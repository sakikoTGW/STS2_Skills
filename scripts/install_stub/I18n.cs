namespace InstallLauncher;

internal enum Lang
{
    Zh,
    En,
}

internal static class I18n
{
    public static Lang Current { get; set; } = Lang.Zh;

    public static string T(string zh, string en) => Current == Lang.Zh ? zh : en;

    public static string AppTitle => T("STS2_Skills 安装程序", "STS2_Skills Setup");
    public static string VersionLine => T("版本 1.0.5", "Version 1.0.5");
    public static string LangLabel => T("语言", "Language");
    public static string LangZh => "中文";
    public static string LangEn => "English";

    public static string HostGroup => T("宿主环境", "Host platform");
    public static string HostStandalone => T("独立 / Cursor / 通用 MCP", "Standalone / Cursor / generic MCP");
    public static string HostHermes => "Hermes Agent";
    public static string HostOpenClaw => "OpenClaw";
    public static string HostAstrBot => "AstrBot";

    public static string PathsGroup => T("安装路径", "Install paths");
    public static string HostPathLabel => T("宿主数据目录", "Host data folder");
    public static string GamePathLabel => T("杀戮尖塔 2 安装目录", "Slay the Spire 2 install folder");
    public static string SkillsPathLabel => T("STS2_Skills 安装目录", "STS2_Skills install folder");
    public static string PythonLabel => T("Python（MCP / pip）", "Python (MCP / pip)");
    public static string CharacterLabel => T("开局角色", "Starting character");

    public static string Browse => T("浏览…", "Browse…");
    public static string Install => T("开始安装", "Install");
    public static string Exit => T("退出", "Exit");
    public static string LogGroup => T("安装日志", "Install log");

    public static string HostPathHintAstrBot => T(
        "一般为 .astrbot\\data（含 plugins、config）",
        "Usually .astrbot\\data (plugins, config)");
    public static string HostPathHintOpenClaw => T(
        "一般为 .openclaw 主目录",
        "Usually .openclaw home folder");
    public static string HostPathHintHermes => T(
        "一般为 .hermes 主目录",
        "Usually .hermes home folder");
    public static string HostPathHintStandalone => T(
        "配置与 Skill 目标目录",
        "Config and skill target folder");
    public static string GamePathHint => T(
        "需包含 SlayTheSpire2.exe",
        "Must contain SlayTheSpire2.exe");

    public static string CharacterName(int index) => index switch
    {
        0 => T("0 · 铁甲战士", "0 · Ironclad"),
        1 => T("1 · 静默猎手", "1 · Silent"),
        2 => T("2 · 故障机器人", "2 · Defect"),
        3 => T("3 · 亡灵契约师", "3 · Necrobinder"),
        4 => T("4 · 储君", "4 · Regent"),
        _ => index.ToString(),
    };

    public static string ErrHostPath => T("请选择有效的宿主目录。", "Please select a valid host folder.");
    public static string ErrGamePath => T("未找到 SlayTheSpire2.exe，请检查游戏目录。", "SlayTheSpire2.exe not found. Check game folder.");
    public static string ErrSkillsPath => T("请指定 STS2_Skills 安装目录。", "Please specify STS2_Skills install folder.");
    public static string ErrPayload => T(
        "安装包内缺少 payload.zip，请重新构建 sts2skill.exe。",
        "Missing embedded payload.zip. Rebuild sts2skill.exe.");
    public static string DoneTitle => T("安装完成", "Installation complete");
    public static string DoneBody => T(
        "1. 启动游戏并启用 STS2 MCP 模组\n2. OpenClaw：重载 MCP / gateway restart\n3. AstrBot：重载 MCP 与插件，/sts2ai ping\n4. 命令行：sts2 ping",
        "1. Launch the game and enable STS2 MCP mod\n2. OpenClaw: reload MCP or gateway restart\n3. AstrBot: reload MCP + plugin, /sts2ai ping\n4. CLI: sts2 ping");
    public static string FailTitle => T("安装失败", "Installation failed");

    public static string StepExtract => T("[1/4] 解压 STS2_Skills", "[1/4] Extract STS2_Skills");
    public static string StepMod => T("[2/4] 安装 STS2MCP 模组", "[2/4] Install STS2MCP mod");
    public static string StepHost => T("[3/4] 配置宿主", "[3/4] Configure host");
    public static string StepPip => T("[4/4] pip 依赖", "[4/4] pip dependencies");
    public static string Installing => T("正在安装，请稍候…", "Installing, please wait…");

    public static string PickFolderTitle(string purpose) =>
        T($"选择文件夹 — {purpose}", $"Select folder — {purpose}");

    public static string PickPythonTitle => T("选择 python.exe", "Select python.exe");
}
