from config import conf


def tips_msg():
    help_text = ''
    if conf().get('token_billing'):
        help_text += """Hi，很高兴认识你，我是 AI 机器人。
    这是我的自我介绍：
    1.在使用前，向我微信转账就可以自动完成充值了。建议1元起充。
    就在刚才我免费为你充值了1元。
    2.在聊天框发送#查询余额 : 可以查询你账号剩下的余额。
    我默认被设置为，最长记得我们的12条对话。
    3.在聊天框对我发送#清空 : 这样我会抹去记忆，与你开始一段新对话。
    这能够节约算力以节省对余额的消耗。
    4.你可以随时拍一拍我，以查看本说明。
    5.并且，欢迎将我的微信推荐给你的其他朋友。
    6.我随时会被增强能力，现在我的版本号是2024.M615。

    我是由 GPT-4o 精心训练而来 ，因此我能协助你：
    T1. 对你发出的文字、语音进行超高质量的回复。
    T2. 对你发的要求快速响应生成图片。
    T3. 对你发的图片和文档（Word、PDF），进行高质量的理解和回答。

    好了，有什么需要帮助的吗？"""
    else:
        help_text += """Hi
        我是由MBM AI 设计的机器人。有什么可以帮你的吗？
        使用技巧：
        在聊天框对我发送#清空 : 这样我会抹去记忆，与你开始一段新对话。"""

    return help_text


def gift_msg():
    help_text = '您的1元体验金已到账，请随时向我提问吧'

    return help_text
