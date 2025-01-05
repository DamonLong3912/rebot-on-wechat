import re

from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from common.log import logger
from common.tmp_dir import TmpDir
from config import conf
from lib import itchat
from lib.itchat.content import *
from utils import mysql_utils
import xml.etree.ElementTree as ET

class WechatMessage(ChatMessage):
    def __init__(self, itchat_msg, is_group=False):
        super().__init__(itchat_msg)
        self.msg_id = itchat_msg["MsgId"]
        self.create_time = itchat_msg["CreateTime"]
        self.is_group = is_group

        notes_join_group = ["加入群聊", "加入了群聊", "invited", "joined"]  # 可通过添加对应语言的加入群聊通知中的关键词适配更多
        notes_bot_join_group = ["邀请你", "invited you", "You've joined", "你通过扫描"]
        notes_exit_group = ["移出了群聊", "removed"]  # 可通过添加对应语言的踢出群聊通知中的关键词适配更多
        notes_patpat = ["拍了拍我", "tickled my", "tickled me"] # 可通过添加对应语言的拍一拍通知中的关键词适配更多

        if itchat_msg["Type"] == TEXT:
            self.ctype = ContextType.TEXT
            self.content = itchat_msg["Text"]
        elif itchat_msg["Type"] == VOICE:
            self.ctype = ContextType.VOICE
            self.content = TmpDir().path() + itchat_msg["FileName"]  # content直接存临时目录路径
            self._prepare_fn = lambda: itchat_msg.download(self.content)
        elif itchat_msg["Type"] == PICTURE and itchat_msg["MsgType"] == 3:
            self.ctype = ContextType.IMAGE
            self.content = TmpDir().path() + itchat_msg["FileName"]  # content直接存临时目录路径
            self._prepare_fn = lambda: itchat_msg.download(self.content)
        elif itchat_msg["Type"] == NOTE and itchat_msg["MsgType"] == 10000:
            if is_group:
                if any(note_bot_join_group in itchat_msg["Content"] for note_bot_join_group in notes_bot_join_group):  # 邀请机器人加入群聊
                    logger.warn("机器人加入群聊消息，不处理~")
                    pass
                elif any(note_join_group in itchat_msg["Content"] for note_join_group in notes_join_group): # 若有任何在notes_join_group列表中的字符串出现在NOTE中
                # 这里只能得到nickname， actual_user_id还是机器人的id
                    if "加入群聊" not in itchat_msg["Content"]:
                        self.ctype = ContextType.JOIN_GROUP
                        self.content = itchat_msg["Content"]
                        if "invited" in itchat_msg["Content"]: # 匹配英文信息
                            self.actual_user_nickname = re.findall(r'invited\s+(.+?)\s+to\s+the\s+group\s+chat', itchat_msg["Content"])[0]
                        elif "joined" in itchat_msg["Content"]: # 匹配通过二维码加入的英文信息
                            self.actual_user_nickname = re.findall(r'"(.*?)" joined the group chat via the QR Code shared by', itchat_msg["Content"])[0]
                        elif "加入了群聊" in itchat_msg["Content"]:
                            self.actual_user_nickname = re.findall(r"\"(.*?)\"", itchat_msg["Content"])[-1]
                    elif "加入群聊" in itchat_msg["Content"]:
                        self.ctype = ContextType.JOIN_GROUP
                        self.content = itchat_msg["Content"]
                        self.actual_user_nickname = re.findall(r"\"(.*?)\"", itchat_msg["Content"])[0]

                elif any(note_exit_group in itchat_msg["Content"] for note_exit_group in notes_exit_group):  # 若有任何在notes_exit_group列表中的字符串出现在NOTE中
                    self.ctype = ContextType.EXIT_GROUP
                    self.content = itchat_msg["Content"]
                    self.actual_user_nickname = re.findall(r"\"(.*?)\"", itchat_msg["Content"])[0]

                elif any(note_patpat in itchat_msg["Content"] for note_patpat in notes_patpat):  # 若有任何在notes_patpat列表中的字符串出现在NOTE中:
                    self.ctype = ContextType.PATPAT
                    self.content = itchat_msg["Content"]
                    if "拍了拍我" in itchat_msg["Content"]:  # 识别中文
                        self.actual_user_nickname = re.findall(r"\"(.*?)\"", itchat_msg["Content"])[0]
                    elif "tickled my" in itchat_msg["Content"] or "tickled me" in itchat_msg["Content"]:
                        self.actual_user_nickname = re.findall(r'^(.*?)(?:tickled my|tickled me)', itchat_msg["Content"])[0]
                else:
                    raise NotImplementedError("Unsupported note message: " + itchat_msg["Content"])
                    
            elif "你已添加了" in itchat_msg["Content"]:  #通过好友请求
                self.ctype = ContextType.ACCEPT_FRIEND
                self.content = itchat_msg["Content"]
            elif any(note_patpat in itchat_msg["Content"] for note_patpat in notes_patpat):  # 若有任何在notes_patpat列表中的字符串出现在NOTE中:
                self.ctype = ContextType.PATPAT
                self.content = itchat_msg["Content"]
            else:
                raise NotImplementedError("Unsupported note message: " + itchat_msg["Content"])
        elif itchat_msg["Type"] == ATTACHMENT:
            self.ctype = ContextType.FILE
            self.content = TmpDir().path() + itchat_msg["FileName"]  # content直接存临时目录路径
            self._prepare_fn = lambda: itchat_msg.download(self.content)
        elif itchat_msg["Type"] == SHARING:
            self.ctype = ContextType.SHARING
            self.content = itchat_msg.get("Url")
        elif itchat_msg["Type"] == FRIENDS:
            self.ctype = ContextType.ACCEPT_FRIEND
            self.content = itchat_msg.get("RecommendInfo")
        # token计费则 放行转账
        elif itchat_msg["Type"] == NOTE and itchat_msg["MsgType"] == 49 and conf().get('token_billing'):
            pass
            
        else:
            raise NotImplementedError("Unsupported message type: Type:{} MsgType:{}".format(itchat_msg["Type"], itchat_msg["MsgType"]))

        self.from_user_id = itchat_msg["FromUserName"]
        self.to_user_id = itchat_msg["ToUserName"]

        user_id = itchat.instance.storageClass.userName
        nickname = itchat.instance.storageClass.nickName

        # 虽然from_user_id和to_user_id用的少，但是为了保持一致性，还是要填充一下
        # 以下很繁琐，一句话总结：能填的都填了。
        if self.from_user_id == user_id:
            self.from_user_nickname = nickname
        if self.to_user_id == user_id:
            self.to_user_nickname = nickname
        try:  # 陌生人时候, User字段可能不存在
            # my_msg 为True是表示是自己发送的消息
            self.my_msg = itchat_msg["ToUserName"] == itchat_msg["User"]["UserName"] and \
                          itchat_msg["ToUserName"] != itchat_msg["FromUserName"]
            self.other_user_id = itchat_msg["User"]["UserName"]
            self.other_user_nickname = itchat_msg["User"]["NickName"]
            if self.other_user_id == self.from_user_id:
                self.from_user_nickname = self.other_user_nickname
            if self.other_user_id == self.to_user_id:
                self.to_user_nickname = self.other_user_nickname
            if itchat_msg["User"].get("Self"):
                # 自身的展示名，当设置了群昵称时，该字段表示群昵称
                self.self_display_name = itchat_msg["User"].get("Self").get("DisplayName")
        except KeyError as e:  # 处理偶尔没有对方信息的情况
            logger.warn("[WX]get other_user_id failed: " + str(e))
            if self.from_user_id == user_id:
                self.other_user_id = self.to_user_id
            else:
                self.other_user_id = self.from_user_id

        if self.is_group:
            self.is_at = itchat_msg["IsAt"]
            self.actual_user_id = itchat_msg["ActualUserName"]
            if self.ctype not in [ContextType.JOIN_GROUP, ContextType.PATPAT, ContextType.EXIT_GROUP]:
                self.actual_user_nickname = itchat_msg["ActualNickName"]





        # 查询余额和转账处理
        try:
            # 指令不处理
            if self.ctype == ContextType.TEXT and self.content.startswith('#'):
                try:
                    remark_name = itchat_msg["User"]["RemarkName"]
                except KeyError as e:  # 处理偶尔没有对方信息的情况
                    remark_name = ''

                attr_status = nickname + '#' + str(itchat_msg["User"]["AttrStatus"])
                self.attr_status = attr_status
                self.remark_name = remark_name
                pass
            # 群聊和自己发的消息不处理和加好友不做处理,ContextType.EXIT_GROUP不做处理,拍一拍不做处理
            elif (is_group is False and self.my_msg == False and self.ctype != ContextType.ACCEPT_FRIEND
                  and self.ctype != ContextType.EXIT_GROUP and self.ctype != ContextType.PATPAT):

                try:
                    remark_name = itchat_msg["User"]["RemarkName"]
                except KeyError as e:  # 处理偶尔没有对方信息的情况
                    remark_name = ''

                attr_status = nickname + '#' + str(itchat_msg["User"]["AttrStatus"])
                self.attr_status = attr_status
                self.remark_name = remark_name

                # 若是转账请求
                if itchat_msg["Type"] == NOTE and itchat_msg["MsgType"] == 49:
                    # 充值金额
                    recharge_amount = None
                    # 充值状态
                    recharge_status = None
                    # 解析XML数据
                    # Parse XML data
                    root = ET.fromstring(itchat_msg["Content"])
                    # Find the 'feedesc' element and get its text
                    feedesc_element = root.find('.//feedesc')
                    if feedesc_element is not None:
                        recharge_amount = float(str(feedesc_element.text).replace('￥', '', 1))

                    paysubtype_element = root.find('.//paysubtype')
                    if paysubtype_element is not None:
                        recharge_status = int(paysubtype_element.text)

                    if recharge_amount is not None and recharge_status is not None:
                        # 1是转账未领取，3是领取转账，为了实时性，未领取时就算充值成功，后面再领取
                        if recharge_status == 1:
                            is_insert = mysql_utils.insert_user(remark_name=remark_name,
                                                                recharge_amount=recharge_amount,
                                                                attr_status=attr_status)
                            if is_insert:
                                receiver = itchat_msg['FromUserName']
                                reply = Reply(ReplyType.TEXT,
                                              f"收到您的{recharge_amount}元奖励，我们满电出发！请重复您的问题呢。")
                                itchat.send(reply.content, toUserName=receiver)
                            else:
                                # 异常
                                receiver = itchat_msg['FromUserName']
                                reply = Reply(ReplyType.TEXT, "充电异常")
                                itchat.send(reply.content, toUserName=receiver)

                        elif recharge_status == 3:
                            pass
                        else:
                            # 异常
                            receiver = itchat_msg['FromUserName']
                            reply = Reply(ReplyType.TEXT, "充电异常")
                            itchat.send(reply.content, toUserName=receiver)
                    # 转账处理到这里就结束了，不往下走
                    raise NotImplementedError(
                        "Unsupported message type: Type:{} MsgType:{}".format(itchat_msg["Type"],
                                                                              itchat_msg["MsgType"]))
                else:
                    # 若token计费
                    if conf().get('token_billing'):
                        user_data = None
                        # 优先用备注名
                        if remark_name is not None and remark_name != "":
                            user_data = mysql_utils.select_user(remark_name=remark_name)
                        if user_data == None:
                            user_data = mysql_utils.select_user(attr_status=attr_status)

                        if user_data is not None and remark_name is not None and remark_name != '' and remark_name != \
                                user_data['remark_name']:
                            mysql_utils.uptdate_user(remark_name=remark_name,
                                                     attr_status=attr_status, id=user_data['id'])

                        if user_data is None:
                            # receiver = itchat_msg['FromUserName']
                            # reply = Reply(ReplyType.TEXT, f"啊欧，{nickname} 似乎累晕了，试试转账功能，给我充充电呢？")
                            # itchat.send(reply.content, toUserName=receiver)
                            # raise NotImplementedError(f"啊欧，{nickname} 似乎累晕了，试试转账功能，给我充充电呢？")
                            # 免费充一元
                            mysql_utils.insert_user(remark_name=remark_name,
                                                    recharge_amount=1,
                                                    attr_status=attr_status)
                        elif float(user_data['recharge_amount']) - float(user_data['quota_used']) <= 0:
                            receiver = itchat_msg['FromUserName']
                            reply = Reply(ReplyType.TEXT,
                                          f"啊欧，{nickname} 似乎累晕了，试试转账功能，给我充充电呢？")
                            itchat.send(reply.content, toUserName=receiver)
                            raise NotImplementedError(f"啊欧，{nickname} 似乎累晕了，试试转账功能，给我充充电呢？")

        except Exception as a:
            raise NotImplementedError(str(a))















