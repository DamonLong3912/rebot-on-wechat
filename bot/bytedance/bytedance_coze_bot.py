# encoding:utf-8
import os
import threading
import time
from typing import List, Tuple

import markdown
import requests
from bs4 import BeautifulSoup
from requests import Response

from bot.bot import Bot
from bot.chatgpt.chat_gpt_session import ChatGPTSession
from bot.session_manager import SessionManager
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common import memory
from common.log import logger
from common.utils import parse_markdown_text
from config import conf
from utils import mysql_utils
from bridge.context import ContextType, Context
from cozepy import MessageType, Message
from os.path import isfile
from urllib.parse import urlparse, unquote
from common.tmp_dir import TmpDir
class ByteDanceCozeBot(Bot):
    def __init__(self):
        super().__init__()
        self.sessions = SessionManager(ChatGPTSession, model=conf().get("model") or "coze")
        # 微信支持的文件扩展名
        self.SUPPORTED_EXTENSIONS = {
            '.bmp',  '.gif', '.mp3', '.wma', '.wav', '.amr',
            '.mp4', '.avi', '.mkv', '.mov', '.doc', '.docx', '.xls', '.xlsx', '.ppt',
            '.pptx', '.pdf', '.txt', '.zip', '.rar'
        }

    def reply(self, query, context=None):
        # acquire reply content
        if context.type == ContextType.TEXT:
            logger.info("[COZE] query={}".format(query))
            session_id = context["session_id"]

            # 处理图片
            img_cache = memory.USER_IMAGE_CACHE.get(context["session_id"])
            if img_cache and conf().get("image_recognition"):
                response, err = self.file_completion(img_cache, file_type='image')
                # 报错与否都删除图片，避免循环异常
                memory.USER_IMAGE_CACHE[context["session_id"]] = None
                if err:
                    return {"completion_tokens": 0, "content": f"识别图片异常, {err}"}

                query = query + ' ' + response['url']

            # 处理文件
            file_cache = memory.USER_FILE_CACHE.get(context["session_id"])
            if file_cache:
                response, err = self.file_completion(file_cache, file_type='file')
                # 报错与否都删除，避免循环异常
                memory.USER_FILE_CACHE[context["session_id"]] = None
                if err:
                    return {"completion_tokens": 0, "content": f"识别文件异常, {err}"}

                query = query + ' ' + response['url']
                # 报错与否都删除图片，避免循环异常
                memory.USER_FILE_CACHE[context["session_id"]] = None

            # 处理URL
            url_cache = memory.USER_URL_CACHE.get(context["session_id"])
            if url_cache:
                query = query + ' ' + url_cache['path']
                # 报错与否都删除图片，避免循环异常
                memory.USER_URL_CACHE[context["session_id"]] = None

            session = self.sessions.session_query(query, session_id)
            logger.debug("[COZE] session query={}".format(session.messages))
            reply_content, err = self._reply_text(session_id, session)
            if err is not None:
                logger.error("[COZE] reply error={}".format(err))
                return Reply(ReplyType.ERROR, "我暂时遇到了一些问题，请您稍后重试~")
            logger.debug(
                "[COZE] new_query={}, session_id={}, reply_cont={}, completion_tokens={}".format(
                    session.messages,
                    session_id,
                    reply_content["content"],
                    reply_content["completion_tokens"],
                )
            )

            # 存session
            self.sessions.session_reply(reply_content["content"], session_id, reply_content["completion_tokens"])

            channel = context.get("channel")
            is_group = context.get("isgroup", False)
            # 尝试mackdown转微信
            html = markdown.markdown(reply_content["content"])

            """
                从 HTML 内容中提取段落和图片链接。
                """
            soup = BeautifulSoup(html, 'html.parser')
            content_list = []
            texts = ''
            # 过滤出我们关心的 HTML 标签
            for element in soup.find_all(['p', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'img']):
                if element.name == 'img':
                    if texts != '':
                        content_list.append({
                            'type': 'text',
                            'content': texts
                        })
                        texts = ''
                    content_list.append({
                        'type': 'image',
                        'content': element['src'],  # 提取图片的 src 属性
                        'alt': element.get('alt', 'Image')  # 提取 alt 属性，如果没有则默认 'Image'
                    })
                elif element.name == 'a':
                    if texts != '':
                        content_list.append({
                            'type': 'text',
                            'content': texts
                        })
                        texts = ''

                    link = element['href']

                    if self.is_image_url(link):
                        # 处理包含图片的链接
                        content_list.append({
                            'type': 'image',
                            'content': link
                        })
                    else:
                        # 处理普通链接
                        content_list.append({
                            'type': 'link',
                            'content': link
                        })
                else:
                    # 处理普通文本
                    # text_parts = []
                    # for content in element.contents:
                    #     if isinstance(content, str):
                    #         text_parts.append(content)
                    #     elif content.name != 'a':  # 忽略<a>标签中的文本
                    #         text_parts.append(content.get_text())

                    texts += (element.get_text() + '\n')

            if texts != '':
                content_list.append({
                    'type': 'text',
                    'content': texts
                })

            for content in content_list[:-1]:
                if content['type'] == 'image':
                    url = content['content']
                    reply = Reply(ReplyType.IMAGE_URL, url)
                    thread = threading.Thread(target=channel.send, args=(reply, context))
                    thread.start()
                elif content['type'] == 'text' or content['type'] == 'link':
                    if content['content'].find('txmov2.a.kwimgs.com') != -1 or content['content'].find(
                            'alimov2.a.kwimgs.com') != -1 or content['content'].find(
                        'cdn.video.picasso.dandanjiang.tv') != -1:
                        reply = Reply(ReplyType.VIDEO_URL, content['content'])
                    elif self.is_file_url(content['content']):
                        file_path = self._download_file(content['content'])
                        if file_path:
                            reply = Reply(ReplyType.FILE, file_path)
                    elif is_group:
                        at_prefix = "@" + context["msg"].actual_user_nickname + "\n"
                        content['content'] = at_prefix + content['content']
                        reply = Reply(ReplyType.TEXT, content['content'].rstrip('-\n\r\n'))
                    else:
                        reply = Reply(ReplyType.TEXT, content['content'].rstrip('-\n\r\n'))
                    channel.send(reply, context)

            # 最后一条消息
            final_item = content_list[-1]
            final_reply = None
            if final_item['type'] == 'text' or final_item['type'] == 'link':
                content = final_item['content']

                if content.find('txmov2.a.kwimgs.com') != -1 or content.find(
                        'alimov2.a.kwimgs.com') != -1 or content.find(
                    'cdn.video.picasso.dandanjiang.tv') != -1:
                    final_reply = Reply(ReplyType.VIDEO_URL, content)
                elif self.is_file_url(content):
                    file_path = self._download_file(content)
                    if file_path:
                        final_reply = Reply(ReplyType.FILE, file_path)
                elif is_group:
                    at_prefix = "@" + context["msg"].actual_user_nickname + "\n"
                    content = at_prefix + content
                    final_reply = Reply(ReplyType.TEXT, content.rstrip('-\n\r\n'))
                else:
                    final_reply = Reply(ReplyType.TEXT, content.rstrip('-\n\r\n'))
            elif final_item['type'] == 'image':
                url = final_item['content']
                final_reply = Reply(ReplyType.IMAGE_URL, url)

            # 若token计费
            if conf().get('token_billing'):
                # 异步扣费
                t = threading.Thread(target=self._fee_deduction, args=(reply_content, context))
                t.start()  # 启动线程

            return final_reply
        else:
            reply = Reply(ReplyType.ERROR, "Bot不支持处理{}类型的消息".format(context.type))
            return reply

    def _get_api_base_url(self):
        return conf().get("coze_api_base", "https://api.coze.cn/open_api/v2")

    def _get_headers(self):
        return {
            'Authorization': f"Bearer {conf().get('coze_api_key', '')}"
        }

    def _get_payload(self, user: str, query: str, chat_history: List[dict]):
        return {
            'bot_id': conf().get('coze_bot_id'),
            "user": user,
            "query": query,
            "chat_history": chat_history,
            "stream": False
        }

    def _reply_text(self, session_id: str, session: ChatGPTSession, retry_count=0):
        try:
            query, chat_history = self._convert_messages_format(session.messages)
            base_url = self._get_api_base_url()
            chat_url = f'{base_url}/chat'
            headers = self._get_headers()
            payload = self._get_payload(session.session_id, query, chat_history)
            response = requests.post(chat_url, headers=headers, json=payload)
            if response.status_code != 200:
                error_info = f"[COZE] response text={response.text} status_code={response.status_code}"
                logger.warn(error_info)
                return None, error_info
            answer, err = self._get_completion_content(response)
            if err is not None:
                return None, err
            completion_tokens, total_tokens = self._calc_tokens(session.messages, answer)
            return {
                "total_tokens": total_tokens,
                "completion_tokens": completion_tokens,
                "content": answer
            }, None
        except Exception as e:
            if retry_count < 2:
                time.sleep(3)
                logger.warn(f"[COZE] Exception: {repr(e)} 第{retry_count + 1}次重试")
                return self._reply_text(session_id, session, retry_count + 1)
            else:
                return None, f"[COZE] Exception: {repr(e)} 超过最大重试次数"

    def _convert_messages_format(self, messages) -> Tuple[str, List[dict]]:
        # [
        #     {"role":"user","content":"你好"，"content_type":"text"},
        #     {"role":"assistant","type":"answer","content":"你好，请问有什么可以帮助你的吗？"，"content_type":"text"}
        #  ]
        chat_history = []
        for message in messages:
            role = message.get('role')
            if role == 'user':
                content = message.get('content')
                chat_history.append({"role": "user", "content": content, "content_type": "text"})
            elif role == 'assistant':
                content = message.get('content')
                chat_history.append({"role": "assistant", "type": "answer", "content": content, "content_type": "text"})
            elif role == 'system':
                # TODO: deal system message
                pass
        user_message = chat_history.pop()
        if user_message.get('role') != 'user' or user_message.get('content', '') == '':
            raise Exception('no user message')
        query = user_message.get('content')
        logger.debug("[COZE] converted coze messages: {}".format([item for item in chat_history]))
        logger.debug("[COZE] user content as query: {}".format(query))
        return query, chat_history

    def _get_completion_content(self, response: Response):
        json_response = response.json()
        if json_response['msg'] != 'success':
            return None, f"[COZE] Error: {json_response['msg']}"
        answer = None
        for message in json_response['messages']:
            if message.get('type') == 'answer':
                answer = message.get('content')
                break
        if not answer:
            return None, "[COZE] Error: empty answer"
        return answer, None

    def _calc_tokens(self, messages, answer):
        # 简单统计token
        completion_tokens = len(answer)
        prompt_tokens = 0
        for message in messages:
            prompt_tokens += len(message["content"])
        return completion_tokens, prompt_tokens + completion_tokens

    # 判定链接是否为图片
    def is_image_url(s, url):
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp']
        return any(url.lower().endswith(ext) or ext + '?' in url.lower() for ext in image_extensions)

    # 判定链接是否为文件
    def is_file_url(s, url):
        # 解析URL
        parsed_url = urlparse(url)
        # 获取文件路径
        file_path = parsed_url.path
        # 提取文件扩展名
        file_extension = file_path.split('.')[-1].lower() if '.' in file_path else ''
        # 检查扩展名是否在支持列表中
        return f".{file_extension}" in s.SUPPORTED_EXTENSIONS

    def file_completion(self, img_cache: dict, file_type=None):
        msg = img_cache.get("msg")
        path = img_cache.get("path")
        msg.prepare()
        logger.info(f"[DOZE] query with images/file, path={path}")

        chat_url = 'https://openai-service.mbmzone.com/api/oss/uploadOSS'
        headers = {'accessKey': '3d8562824fba6f54b1c54c185d65876c'}

        response = None
        err = None
        with open(path, 'rb') as file:
            if file_type is None or file_type == 'image':
                files = {'file': (path, file, 'image/png')}
            else:
                files = {'file': (path, file)}
            res = requests.post(url=chat_url, files=files, headers=headers)
            if res.status_code == 200:
                try:
                    response = {'url': res.json()['data']['url']}
                except Exception as e:
                    err = e
            else:
                logger.error(f"[CHATGPT] vision completion, status_code={res.status_code}, response={res.text}")
                err = res.text

        os.remove(path)
        return response, err

    # 扣费
    def _fee_deduction(self, reply_content, context):

        if context.kwargs['isgroup']:
            pass
        else:
            remark_name = context.kwargs['msg'].remark_name
            attr_status = context.kwargs['msg'].attr_status
            # 扣费
            # 输入
            prompt_tokens = reply_content['total_tokens'] - reply_content['completion_tokens']
            # 输出
            completion_tokens = reply_content['completion_tokens']

            input_multiple = conf().get('input_multiple', 3)
            output_multiple = conf().get('output_multiple', 2)

            # 价格先随意
            prompt_price = 0.000005 * prompt_tokens * input_multiple
            completion_price = 0.000015 * completion_tokens * output_multiple

            total = float(prompt_price + completion_price)
            if total < 0.01:
                total = 0.01
            f = mysql_utils.fee_deduction(remark_name, total,
                                          attr_status)
            if not f:
                mysql_utils.fee_deduction(remark_name, total,
                                          attr_status)




    def _download_file(self, url):
        try:
            response = requests.get(url)
            response.raise_for_status()
            parsed_url = urlparse(url)
            logger.debug(f"Downloading file from {url}")
            url_path = unquote(parsed_url.path)
            # 从路径中提取文件名
            file_name = url_path.split('/')[-1]
            logger.debug(f"Saving file as {file_name}")
            file_path = os.path.join(TmpDir().path(), file_name)
            with open(file_path, 'wb') as file:
                file.write(response.content)
            return file_path
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
        return None



    # def get_parsed_reply(self, messages: list[Message], context: Context = None):
    #     parsed_content = None
    #     for message in messages:
    #         if message.type == MessageType.ANSWER:
    #             conte = parse_markdown_text(message.content)
    #             if parsed_content is None:
    #                 parsed_content = conte
    #             else:
    #                 parsed_content.append(conte)
    #
    #         # {"answer": "![image](/files/tools/dbf9cd7c-2110-4383-9ba8-50d9fd1a4815.png?timestamp=1713970391&nonce=0d5badf2e39466042113a4ba9fd9bf83&sign=OVmdCxCEuEYwc9add3YNFFdUpn4VdFKgl84Cg54iLnU=)"}
    #     at_prefix = ""
    #     channel = context.get("channel")
    #     is_group = context.get("isgroup", False)
    #     if is_group:
    #         at_prefix = "@" + context["msg"].actual_user_nickname + "\n"
    #     for item in parsed_content[:-1]:
    #         reply = None
    #         if item['type'] == 'text':
    #             content = at_prefix + item['content']
    #             reply = Reply(ReplyType.TEXT, content)
    #         elif item['type'] == 'image':
    #             image_url = self._fill_file_base_url(item['content'])
    #             image = self._download_image(image_url)
    #             if image:
    #                 reply = Reply(ReplyType.IMAGE, image)
    #             else:
    #                 reply = Reply(ReplyType.TEXT, f"图片链接：{image_url}")
    #         elif item['type'] == 'file':
    #             file_url = self._fill_file_base_url(item['content'])
    #             if isfile(file_url):
    #                 file_path = self._download_file(file_url)
    #                 if file_path:
    #                     reply = Reply(ReplyType.FILE, file_path)
    #             else:
    #                 reply = Reply(ReplyType.TEXT, f"链接：{file_url}")
    #         logger.debug(f"[COZE] reply={reply}")
    #         if reply and channel:
    #             channel.send(reply, context)
    #
    #     final_item = parsed_content[-1]
    #     final_reply = None
    #     if final_item['type'] == 'text':
    #         content = final_item['content']
    #         if is_group:
    #             at_prefix = "@" + context["msg"].actual_user_nickname + "\n"
    #             content = at_prefix + content
    #         final_reply = Reply(ReplyType.TEXT, final_item['content'])
    #     elif final_item['type'] == 'image':
    #         image_url = self._fill_file_base_url(final_item['content'])
    #         image = self._download_image(image_url)
    #         if image:
    #             final_reply = Reply(ReplyType.IMAGE, image)
    #         else:
    #             final_reply = Reply(ReplyType.TEXT, f"图片链接：{image_url}")
    #     elif final_item['type'] == 'file':
    #         file_url = self._fill_file_base_url(final_item['content'])
    #         if isfile(file_url):
    #             file_path = self._download_file(file_url)
    #             if file_path:
    #                 final_reply = Reply(ReplyType.FILE, file_path)
    #         else:
    #             final_reply = Reply(ReplyType.TEXT, f"链接：{file_url}")
    #     return final_reply, None
