"""Apply reviewed overrides and versioned translations without replacing source evidence."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 官方中文术语归一化表。必须“长词优先、具体优先”，后续短词规则才不会被前面的替换破坏。
# 目标：把离线机器翻译里的产品名/考试术语统一成 Microsoft 官方简体中文说法。
# 每条映射的结果都不包含其自身，因此重复执行是幂等的。
TERMINOLOGY = [
    # ================= A. 复合产品名 / 角色（最长优先） =================
    ("微软Cloud卫士微软哨兵", "Microsoft Defender for Cloud 与 Microsoft Sentinel"),
    ("微软云卫士微软哨兵", "Microsoft Defender for Cloud 与 Microsoft Sentinel"),
    ("微软办公室维护者的威胁保护状况报告 365", "Microsoft Defender for Office 365 的威胁防护状态报告"),
    ("微软办公室维护者的威胁保护状况报告 36", "Microsoft Defender for Office 365 的威胁防护状态报告"),
    ("微软维护者365办公室", "Microsoft Defender for Office 365"),
    ("微软维护者办公室365", "Microsoft Defender for Office 365"),
    ("Microsoft 365维权门", "Microsoft Defender 门户"),
    ("微软365维权门户网站", "Microsoft Defender 门户"),
    ("微软365维权门户", "Microsoft Defender 门户"),
    ("微软 365 维权权限", "Microsoft 365 Defender 权限"),
    ("微软 365 维权者", "Microsoft 365 Defender"),
    ("Microsoft 365 维权者", "Microsoft 365 Defender"),
    ("微软365维权者", "Microsoft 365 Defender"),
    ("微软维权为办公室365", "Microsoft Defender for Office 365"),
    ("微软维权为Cloud", "Microsoft Defender for Cloud"),
    ("微软维权为 Cloud", "Microsoft Defender for Cloud"),
    ("微软维权安全中心", "Microsoft Defender for Cloud"),
    ("微软维权XDR", "Microsoft Defender XDR"),
    ("微软维权者的身份", "Microsoft Defender for Identity"),
    ("微软维权公司", "Microsoft 365 Defender"),
    ("微软维权门户网站", "Microsoft Defender 门户"),
    ("微软维权门户", "Microsoft Defender 门户"),
    ("微软维权员", "Microsoft Defender"),
    ("微软维权者", "Microsoft Defender"),
    ("微软维权", "Microsoft Defender"),
    ("微软维护者Cloud Apps", "Microsoft Defender for Cloud Apps"),
    ("微软 Cloud Apps 维护器", "Microsoft Defender for Cloud Apps"),
    ("微软 Cloud Apps 维护者", "Microsoft Defender for Cloud Apps"),
    ("微软Cloud App安全", "Microsoft Defender for Cloud Apps"),
    ("微软云App安全", "Microsoft Defender for Cloud Apps"),
    ("微软维护云", "Microsoft Defender for Cloud"),
    ("微软身份要求维护者", "Microsoft Defender for Identity 的要求"),
    ("微软身份维护者", "Microsoft Defender for Identity"),
    ("微软捍卫者身份", "Microsoft Defender for Identity"),
    ("微软捍卫者为端点", "Microsoft Defender for Endpoint"),
    ("微软端点要求捍卫者", "Microsoft Defender for Endpoint 的要求"),
    ("微软端点捍卫者", "Microsoft Defender for Endpoint"),
    ("微软端点维护者", "Microsoft Defender for Endpoint"),
    ("微软捍卫者Endpoint", "Microsoft Defender for Endpoint"),
    ("微软捍卫者门户网站", "Microsoft Defender 门户"),
    ("微软捍卫者门户", "Microsoft Defender 门户"),
    ("微软卫士门户网站", "Microsoft Defender 门户"),
    ("微软卫士门户", "Microsoft Defender 门户"),
    ("微软卫士XDR", "Microsoft Defender XDR"),
    ("微软捍卫者XDR", "Microsoft Defender XDR"),
    ("微软卫士365的仪表上", "Microsoft 365 Defender 门户中"),
    ("微软卫士365", "Microsoft 365 Defender"),
    ("微软卫士抗病毒", "Microsoft Defender 防病毒"),
    ("微软卫视Cloud", "Microsoft Defender for Cloud"),
    ("微软卫视的端点", "Microsoft Defender for Endpoint"),
    ("微软卫视", "Microsoft Defender"),
    ("微软服务器维护者计划2", "Microsoft Defender for Servers 计划 2"),
    ("微软服务器维护者和", "Microsoft Defender for Servers 和"),
    ("微软服务器维护者", "Microsoft Defender for Servers"),
    ("微软服务器维护器", "Microsoft Defender for Servers"),
    ("微软服务器捍卫者", "Microsoft Defender for Servers"),
    ("服务器维护者的订阅计划 2", "Defender for Servers 的订阅到计划 2"),
    ("服务器维护者", "Defender for Servers"),
    ("服务器维护器", "Defender for Servers"),
    ("服务器捍卫者", "Defender for Servers"),
    ("微软Cloud卫士", "Microsoft Defender for Cloud"),
    ("微软云卫士", "Microsoft Defender for Cloud"),
    ("Azure 维权计划", "Azure Defender 计划"),
    ("Azure 维权者", "Azure Defender"),
    ("Azure维权者", "Azure Defender"),
    ("Azure 维权员", "Azure Defender"),
    ("Azure 维护者", "Azure Defender"),
    ("Azure卫士", "Azure Defender"),
    ("Azure 卫士", "Azure Defender"),
    ("云层部署维护者", "Defender for Cloud 部署"),
    ("云卫士", "Defender for Cloud"),
    ("微软资源管理器捍卫者", "Microsoft Defender for Resource Manager"),
    ("DNS 的微软捍卫者", "Microsoft Defender for DNS"),
    ("微软App 服务捍卫者", "Microsoft Defender for App Service"),
    ("微软App服务捍卫者", "Microsoft Defender for App Service"),
    ("DevOps 的微软守护程序", "Microsoft Defender for DevOps"),
    ("微软 Cloud 守护者", "Microsoft Defender for Cloud"),
    ("微软捍卫云的强化安全功能", "Microsoft Defender for Cloud 的增强安全功能"),
    ("微软云App安全内置异常探测政策", "Microsoft Defender for Cloud Apps 内置异常检测策略"),
    ("微软维护者", "Microsoft Defender"),
    ("微软维护器", "Microsoft Defender"),
    ("微软捍卫者", "Microsoft Defender"),
    ("微软卫士", "Microsoft Defender"),
    ("微软守护者", "Microsoft Defender"),
    ("微软守护程序", "Microsoft Defender"),
    # ---- Sentinel 角色（必须在“哨兵”替换之前）----
    ("阿苏雷哨兵反击者", "Azure Sentinel Responder"),
    ("阿苏雷哨兵贡献者", "Azure Sentinel Contributor"),
    ("阿苏雷哨兵阅读器", "Azure Sentinel Reader"),
    ("微软哨兵自动化贡献器", "Microsoft Sentinel 自动化参与者"),
    ("微软哨兵贡献者", "Microsoft Sentinel 参与者"),
    ("微软哨兵反击器", "Microsoft Sentinel 响应者"),
    ("微软哨兵阅读器", "Microsoft Sentinel 读取者"),
    ("微软哨兵游戏本", "Microsoft Sentinel Playbook"),
    ("微软 Sentinel 游戏本操作器", "Microsoft Sentinel Playbook 操作员"),
    # ================= B. Sentinel 名称 =================
    ("Azure 哨兵直播流程", "Azure Sentinel 实时流"),
    ("Azure 哨兵", "Azure Sentinel"),
    ("Azure哨兵", "Azure Sentinel"),
    ("阿苏雷哨兵", "Azure Sentinel"),
    ("阿祖尔哨兵", "Azure Sentinel"),
    ("阿苏尔哨兵", "Azure Sentinel"),
    ("微软的哨兵", "Microsoft Sentinel"),
    ("微软《哨兵》", "Microsoft Sentinel"),
    ("Microsoft的哨兵", "Microsoft Sentinel"),
    ("Microsoft 哨兵", "Microsoft Sentinel"),
    ("微软Sentinel", "Microsoft Sentinel"),
    ("微软 Sentinel", "Microsoft Sentinel"),
    ("微软哨兵", "Microsoft Sentinel"),
    ("阿苏雷云壳", "Azure Cloud Shell"),
    ("阿苏雷", "Azure"),
    ("阿祖尔", "Azure"),
    ("阿苏尔", "Azure"),
    # ================= C. 其他 Microsoft 产品 =================
    ("微软监测代理", "Microsoft 监视代理"),
    ("微软监控代理", "Microsoft 监视代理"),
    ("微软安全计分动作", "Microsoft 安全分数操作"),
    ("微软安全计分", "Microsoft 安全分数"),
    ("微软安全评分", "Microsoft 安全分数"),
    ("微软信息保护", "Microsoft 信息保护"),
    ("微软交易所在线", "Microsoft Exchange Online"),
    ("微软365合规中心", "Microsoft Purview 合规门户"),
    ("微软365达标中心", "Microsoft Purview 合规门户"),
    ("微软合规中心", "Microsoft Purview 合规门户"),
    ("微软云安全基准", "Microsoft 云安全基准"),
    ("微软抗疟疾软件扩展", "Microsoft 反恶意软件扩展"),
    ("微软事件创建规则", "Microsoft Sentinel 事件创建规则"),
    ("微软安全副驾驶", "Microsoft Security Copilot"),
    ("微软副驾驶", "Microsoft Security Copilot"),
    ("Microsoft Copilot用于安全", "Microsoft Security Copilot"),
    ("微软365", "Microsoft 365"),
    ("微软 365", "Microsoft 365"),
    ("微软图", "Microsoft Graph"),
    ("微软团队", "Microsoft Teams"),
    ("微软Entra", "Microsoft Entra"),
    ("微软Intune", "Microsoft Intune"),
    ("微软Office", "Microsoft Office"),
    ("Microsoft 维护者", "Microsoft Defender"),
    ("Microsoft维护者", "Microsoft Defender"),
    ("Microsoft 捍卫者", "Microsoft Defender"),
    ("Microsoft 卫士", "Microsoft Defender"),
    ("维德为云", "Microsoft Defender for Cloud"),
    ("守护云", "Defender for Cloud"),
    ("Azure 活动目录", "Azure Active Directory"),
    ("Azure灯塔", "Azure Lighthouse"),
    ("Azure 灯塔", "Azure Lighthouse"),
    ("康托索", "Contoso"),
    ("法布里卡姆", "Fabrikam"),
    # ================= D. 通用回退（剩余中文“维护者/卫士”） =================
    ("维护者", "Defender"),
    ("维护器", "Defender"),
    ("捍卫者", "Defender"),
    ("卫士", "Defender"),
    ("守护者", "Defender"),
    ("守护程序", "Defender"),
    ("守护符", "Defender"),
    ("维权者", "Defender"),
    ("维权", "Defender"),
    ("辩护人", "Defender"),
    ("维护云", "Defender for Cloud"),
    ("哨兵", "Sentinel"),
    ("微软 Defender 用于身份认证", "Microsoft Defender for Identity"),
    ("Microsoft Defender 用于身份认证", "Microsoft Defender for Identity"),
    ("微软 Defender 用于身份验证", "Microsoft Defender for Identity"),
    ("Microsoft Defender 用于身份验证", "Microsoft Defender for Identity"),
    ("Azure Defenders", "Azure Defender"),
    ("微软", "Microsoft"),
    # ================= E. Sentinel 组件 =================
    ("高级威胁搜寻", "高级搜寻"),
    ("打猎的问讯", "搜寻查询"),
    ("打猎", "搜寻"),
    ("问讯", "查询"),
    ("工作手册", "工作簿"),
    ("工作空间", "工作区"),
    ("快速簿", "Playbook"),
    ("一本剧本", "一个 Playbook"),
    ("剧本", "Playbook"),
    ("运行簿", "Runbook"),
    ("速记", "Playbook"),
    ("游戏本", "Playbook"),
    ("预定分析规则", "计划分析规则"),
    ("预定规则", "计划规则"),
    # ================= F. 告警 / 事件 =================
    ("安全提示", "安全警报"),
    ("安全告警", "安全警报"),
    ("警示", "警报"),
    ("告警", "警报"),
    ("高强度提醒", "高严重性警报"),
    ("事件提醒", "事件和警报"),
    ("提醒页面", "警报页面"),
    ("提醒", "警报"),
    ("误报警报", "误报"),
    ("电子邮件警告", "电子邮件警报"),
    ("电子邮件提醒", "电子邮件警报"),
    ("事故", "事件"),
    ("断裂玻璃账户", "应急访问帐户"),
    # ================= G. 响应 / 修正 =================
    ("现场响应", "实时响应"),
    ("现场反应", "实时响应"),
    ("现场环境", "本地环境"),
    ("现场网络", "本地网络"),
    ("立面网络", "本地网络"),
    ("景点网络", "本地网络"),
    ("积极补救行动", "主动修正操作"),
    ("补救行动", "修正操作"),
    ("自动补救", "自动修正"),
    ("补救", "修正"),
    ("反应行动", "响应操作"),
    ("响应程序", "响应操作"),
    ("主动开发", "主动利用"),
    ("块模式", "阻止模式"),
    # ================= H. 登录 =================
    ("签名认证", "登录"),
    ("签名尝试", "登录尝试"),
    ("签名日志", "登录日志"),
    ("签名事件", "登录事件"),
    ("交互式签名", "交互式登录"),
    ("签名时", "登录时"),
    ("签注", "登录"),
    ("签入", "登录"),
    ("签名", "登录"),
    # ================= I. 设备 / 终结点 =================
    ("被Microsoft Defender for Cloud上机", "已载入 Microsoft Defender for Cloud"),
    ("被装入", "已载入"),
    ("上机", "载入"),
    ("装置", "设备"),
    ("端点调查包", "终结点调查包"),
    ("端点检测和响应", "终结点检测和响应"),
    ("端点设置", "终结点设置"),
    ("端点", "终结点"),
    # ================= J. 安全分析术语 =================
    ("虚假的阳性", "误报"),
    ("虚假阳性", "误报"),
    ("虚假的正提示", "误报"),
    ("虚假的正数", "误报"),
    ("虚假正警告", "误报"),
    ("虚假积极", "误报"),
    ("假阳性", "误报"),
    ("不可能旅行", "不可能的旅行"),
    ("残酷的武力攻击", "暴力破解攻击"),
    ("残酷的武力", "暴力破解"),
    ("野蛮武力攻击", "暴力破解攻击"),
    ("野蛮武力", "暴力破解"),
    ("武力攻击", "暴力破解攻击"),
    ("最少特权原则", "最低特权原则"),
    ("多要素认证", "多重身份验证"),
    ("身份认证", "身份验证"),
    ("有条件的准入", "条件访问"),
    ("检测政策", "检测策略"),
    ("政策", "策略"),
    ("安全计分", "安全分数"),
    ("安全评分", "安全分数"),
    ("攻击表面", "攻击面"),
    ("脆弱性管理", "漏洞管理"),
    ("脆弱性", "漏洞"),
    ("脆弱资源", "易受攻击的资源"),
    ("反病毒", "防病毒"),
    ("恶意文物", "恶意项目"),
    ("法证数据", "取证数据"),
    ("审计", "审核"),
    ("数据损失预防", "数据丢失防护"),
    ("数据丢失预防", "数据丢失防护"),
    ("威胁保护", "威胁防护"),
    ("敏感群体", "敏感组"),
    ("活动探索者", "活动资源管理器"),
    ("检疫", "隔离"),
    ("登机", "载入"),
    ("自动提供设备", "自动预配"),
    ("工作负荷", "工作负载"),
    ("工作流程", "工作流"),
    ("颗粒授权管理员权限", "粒度委派管理员权限"),
    ("保密身份管理", "特权身份管理"),
    ("安全行动组", "安全运营团队"),
    ("保安的副驾驶", "Security Copilot"),
    ("安全副驾驶", "Security Copilot"),
    ("副驾驶", "Copilot"),
    ("行政努力", "管理工作量"),
    ("行政工作", "管理工作"),
    ("行政特权", "管理特权"),
    ("展览所示", "所示"),
    ("展览", "示例"),
    ("传送门", "门户"),
    ("门户网站", "门户"),
    ("仪表上", "门户中"),
    ("刀片", "边栏选项卡"),
    ("叶片", "边栏选项卡"),
    ("哪把刀", "哪个边栏选项卡"),
    ("热区域", "Hot Area"),
    ("热气压", "HOTSPOT -"),
    ("安保", "安全"),
    ("抗疟软件", "反恶意软件"),
    ("抗疟", "反恶意软件"),
    ("攻击矢量", "攻击途径"),
    ("电网", "网格"),
    ("报道的事件", "已报告的事件"),
    ("安全会议", "安全会话"),
    ("安全独立经验Copilot", "Security Copilot 独立体验"),
    ("角色任务", "角色分配"),
    ("Microsoft 的 Servers Plan 2", "Microsoft Defender for Servers 计划 2"),
    ("Microsoft Cloud Apps 要求的 Defender", "Microsoft Defender for Cloud Apps 的要求"),
    ("Cloud Plans 的 Defender", "Defender for Cloud 计划"),
    ("Cloud 日志的 Defender", "Defender for Cloud 日志"),
    ("Cloud Apps 的 Defender", "Defender for Cloud Apps"),
    ("Cloud 的 Defender", "Defender for Cloud"),
    ("endpoint 的 Defender", "Defender for Endpoint"),
    ("DevOps 的 Defender", "Defender for DevOps"),
    ("MicrosoftCloud", "Microsoft Cloud"),
    ("登上", "载入"),
    ("直播响应", "实时响应"),
    ("终结点计划 1 的 Defender 许可证", "Defender for Endpoint 计划 1 许可证"),
    ("终结点的 Defender", "Defender for Endpoint"),
    ("终结点调查包的 Defender", "Defender 的终结点调查包"),
    ("“云”Defender”", "Microsoft Defender for Cloud"),
    ("抗病毒", "防病毒"),
    ("创造", "创建"),
    ("发展努力", "开发工作量"),
    ("最少特权的原则", "最低特权原则"),
    ("最少特权", "最低特权"),
    ("个案研究", "案例研究"),
    ("每个案子", "每个案例"),
    ("审查屏幕", "审阅屏幕"),
    ("回望期", "回溯期"),
    ("调谐", "优化"),
    ("警报调制规则", "警报优化规则"),
    ("联盟操作员", "union 运算符"),
    ("项目操作员", "project 运算符"),
    ("汇总操作员", "summarize 运算符"),
    ("操作员在哪里", "where 运算符"),
    ("事件日志的收藏", "事件日志的收集"),
    ("选择 No.", "选择“否”。"),
    ("选择 No", "选择“否”"),
    ("请选择是", "请选择“是”"),
    ("Hot Area :", "Hot Area："),
    ("文物", "项目"),
    ("鲁普(DRAG DROP)", "拖放（DRAG DROP）"),
    # 2026-10-28 补漏：KQL 函数、表名、库名、产品标识被机翻成中文乱词（这些必须保持英文原文）
    ("弹夹", "bin"),
    ("精心策划", "plotly"),
    ("日光灯", "TensorFlow"),
    ("马特普洛特利布( Matplotlib)", "matplotlib"),
    ("马特普洛特利布", "matplotlib"),
    ("微调", "msticpy"),
    ("见 By( )", "SeenBy()"),
    ("见 By", "SeenBy()"),
    ("来自 IP( ) 的设备", "DeviceFromIP()"),
    ("下一个( )", "next()"),
    ("当前_ 集群_ 终结点( )", "current_cluster_endpoint()"),
    ("身份指导活动", "IdentityDirectoryEvents"),
    ("身份 Logon 事件", "IdentityLogonEvents"),
    ("AADRIsky 用户", "AADRiskyUsers"),
    ("安全辅助器", "SecurityAlert"),
    ("扩展 Properies", "ExtendedProperies"),
    ("东道主", "主机"),
    ("警卫", "安全"),
    ("无法进行的旅行", "不可能旅行"),
    ("办公室 365", "Office 365"),
    ("监管合规", "法规符合性"),
    ("接线员", "运算符"),
    ("届会", "会话"),
    ("流媒体", "livestream"),
    ("视觉", "可视化"),
    # 2026-10-28 补漏（第二批）：题面里成片出现的机翻词
    # 注意每条结果都不能再含自己的键（否则重跑会二次替换，破坏幂等）
    ("德拉格·德拖放（DRAG DROP）", "拖放（DRAG DROP）"),
    ("德拉格·德拖放", "拖放"),
    ("Duel1", "Device1"),
    ("上载至", "载入到"),
    ("上载到", "载入到"),
    ("上载", "载入"),
    ("机载设备", "已载入设备"),
    ("妥协指标", "入侵指标"),
    ("报表图像", "报表视图"),
    ("火花可视化", "迷你图（sparkline）"),
    ("残废", "已禁用"),
    ("^ ", "• "),
]


def normalize_zh(text: str) -> str:
    """把机器翻译的术语/标点统一为 Microsoft 官方简体中文写法。"""
    if not text:
        return text
    # 这些“签名”不是 sign-in，不能替换成“登录”
    text = text.replace("数字签名", "DIGSIG")
    text = text.replace("LDAP签名", "LDAPSIG")
    text = text.replace("未签名", "UNSIGNED")
    for old, new in TERMINOLOGY:
        text = text.replace(old, new)
    text = text.replace("DIGSIG", "数字签名")
    text = text.replace("LDAPSIG", "LDAP 签名")
    text = text.replace("UNSIGNED", "未签名")
    # 残留的英文复数标记
    text = text.replace("( S)", "").replace("（S）", "").replace("( S )", "")
    # 中文语境下的半角标点
    text = text.replace("?.", "？").replace("!.", "！")
    text = re.sub(r"(?<=[一-鿿]),\s*(?=[一-鿿])", "，", text)
    text = re.sub(r"(?<=[一-鿿])\.\s*(?=[一-鿿])", "。", text)
    text = re.sub(r"(?<=[一-鿿]),(?=[一-鿿])", "，", text)
    text = re.sub(r"(?<=[0-9]),(?=[一-鿿])", "，", text)
    text = re.sub(r"(?<=[一-鿿])\.(?=[\s\n]|$)", "。", text)
    text = re.sub(r"(?<=[一-鿿])\?(?=[\s\n]|$)", "？", text)
    text = re.sub(r"(?<=[一-鿿])!(?=[\s\n]|$)", "！", text)
    text = re.sub(r"(?<=[一-鿿]);(?=[\s\n]|$)", "；", text)
    text = re.sub(r"(?<=[一-鿿]):(?=[一-鿿]|\s)", "：", text)
    # 中英文之间补空格（Microsoft 中文文档排版习惯）
    text = re.sub(r"(?<=[一-鿿])(?=[A-Za-z0-9])", " ", text)
    text = re.sub(r"(?<=[A-Za-z0-9])(?=[一-鿿])", " ", text)
    return text


def normalize_question(q):
    q["zh"] = normalize_zh(q.get("zh", ""))
    q["case_zh"] = normalize_zh(q.get("case_zh", ""))
    q["explanation_zh"] = normalize_zh(q.get("explanation_zh", ""))
    for o in q.get("options", []):
        o["zh"] = normalize_zh(o.get("zh", ""))
    for s in q.get("slots", []):
        s["zh"] = normalize_zh(s.get("zh", ""))
        for o in s.get("options", []):
            o["zh"] = normalize_zh(o.get("zh", ""))
        for k, v in (s.get("options_zh") or {}).items():
            s["options_zh"][k] = normalize_zh(v)
    return q


def main():
    path = ROOT / "data/question-bank.json"
    bank = json.loads(path.read_text(encoding="utf-8"))
    translations = (
        json.loads((ROOT / "data/translations.json").read_text(encoding="utf-8"))
        if (ROOT / "data/translations.json").exists()
        else {}
    )
    reviewed = (
        json.loads((ROOT / "data/overrides.json").read_text(encoding="utf-8"))
        if (ROOT / "data/overrides.json").exists()
        else {}
    )
    explanations = (
        json.loads((ROOT / "data/explanations.json").read_text(encoding="utf-8"))
        if (ROOT / "data/explanations.json").exists()
        else {}
    )
    for q in bank["questions"]:
        patch = translations.get(q["id"], {})
        q["zh"] = patch.get("zh", q["zh"])
        q["case_zh"] = patch.get("case_zh", q.get("case_zh", ""))
        q["explanation_zh"] = explanations.get(q["id"], q.get("explanation_zh", ""))
        q["translation_status"] = patch.get("translation_status", "pending")
        for o in q["options"]:
            o["zh"] = patch.get("options_zh", {}).get(o["id"], "")
        # 槽位选项（hotspot / matching / ordering）的中文：{"槽位id": {"选项id": "中文"}}
        slots_zh = patch.get("slots_zh") or {}
        if not isinstance(slots_zh, dict):
            slots_zh = {}
        for s in q.get("slots") or []:
            for o in s.get("options") or []:
                text = (slots_zh.get(str(s.get("id"))) or {}).get(str(o["id"]))
                if text:
                    o["zh"] = text
        if q["id"] in reviewed:
            q.update({k: v for k, v in reviewed[q["id"]].items() if k != "options_zh"})
            for o in q["options"]:
                o["zh"] = reviewed[q["id"]].get("options_zh", {}).get(o["id"], o["zh"])
        # 统一官方中文术语（幂等；机器草稿与人工复核文本都处理，保证全库一致）
        normalize_question(q)
    qs = bank["questions"]
    # Version the actual immutable question content, not just the input file.
    bank["source_version"] = bank.get("source_version", bank["version"])
    bank["version"] = hashlib.sha256(json.dumps(qs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[
        :12
    ]
    path.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
    report = dict(
        source_pages=bank["page_count"],
        total=len(qs),
        unique_ids=len({q["id"] for q in qs}),
        topics=dict(Counter(q["topic"] for q in qs)),
        types=dict(Counter(q["type"] for q in qs)),
        statuses=dict(Counter(q["status"] for q in qs)),
        translated=sum(bool(q["zh"]) for q in qs),
        translation_states=dict(Counter(q["translation_status"] for q in qs)),
        review=[dict(id=q["id"], pages=q["pages"], issues=q["issues"]) for q in qs if q["status"] != "ready"],
    )
    (ROOT / "data/import-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "review"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
