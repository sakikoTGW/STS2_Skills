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
    public static string VersionLine => T("版本 1.0.6", "Version 1.0.6");
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
    public static string AdvancedGroup => T("高级（可选）", "Advanced (optional)");
    public static string AutoDetect => T("自动检测路径", "Auto-detect paths");
    public static string ForceReinstall => T("强制重新安装（覆盖已有文件）", "Force reinstall (overwrite existing)");
    public static string StatusReady => T("环境已就绪，路径与 MCP/模组一致，无需重复安装。", "Environment ready — paths and MCP/mod match; no reinstall needed.");
    public static string StatusNeedInstall => T("部分组件未安装或路径不一致，可点击「开始安装」。", "Some components missing or paths differ — click Install.");
    public static string EnvAlreadyReady => T("[跳过] 环境已就绪，未重复安装。", "[skip] Environment already ready; no reinstall.");
    public static string ProbeSkillsOk => T("STS2_Skills 已安装", "STS2_Skills present");
    public static string ProbeSkillsMissing => T("未找到 STS2_Skills", "STS2_Skills missing");
    public static string ProbeSkillsIncomplete => T("STS2_Skills 目录不完整", "STS2_Skills folder incomplete");
    public static string ProbeModOk => T("STS2MCP 模组已安装", "STS2MCP mod present");
    public static string ProbeModMissing => T("未找到 STS2MCP 模组", "STS2MCP mod missing");
    public static string ProbeModNoGame => T("游戏目录无效", "Invalid game folder");
    public static string ProbeHostOk => T("宿主 MCP 已配置且路径一致", "Host MCP configured, paths match");
    public static string ProbeHostMismatch => T("宿主 MCP 未配置或路径不一致", "Host MCP missing or path mismatch");
    public static string ProbeHostMissing => T("宿主目录不存在", "Host folder missing");
    public static string ProbeHostGameMismatch => T("缓存游戏路径与当前选择不一致", "Cached game path differs from selection");
    public static string ProbePipOk => T("Python 可导入 plugins.sts2", "Python can import plugins.sts2");
    public static string ProbePipMissing => T("需 pip install -e", "Needs pip install -e");
    public static string ProbePipNoPython => T("未配置 Python（无法验证 pip）", "Python not configured (pip unchecked)");
    public static string ProbePipNeedSkills => T("需先安装 STS2_Skills", "Install STS2_Skills first");
    public static string StepExtractSkip => T("[跳过] STS2_Skills 已存在", "[skip] STS2_Skills already present");
    public static string StepModSkip => T("[跳过] 模组已安装", "[skip] Mod already installed");
    public static string StepHostSkip => T("[跳过] 宿主 MCP 已配置", "[skip] Host MCP already configured");
    public static string StepPipSkip => T("[跳过] pip / 导入已就绪", "[skip] pip / import already OK");

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
        "自动扫描 Steam / 缓存；需包含 SlayTheSpire2.exe",
        "Auto-scan Steam / cache; must contain SlayTheSpire2.exe");

    public static string ErrHostPath => T("请选择有效的宿主目录，或点「自动检测路径」。", "Select a valid host folder or click Auto-detect paths.");
    public static string ErrGamePath => T(
        "未找到游戏目录。请确认已安装杀戮尖塔 2，或点「自动检测路径」/「浏览」手动选择。",
        "Game folder not found. Install Slay the Spire 2, or use Auto-detect / Browse.");
    public static string ErrSkillsPath => T("请指定 STS2_Skills 安装目录。", "Please specify STS2_Skills install folder.");
    public static string ErrPayload => T(
        "安装包内缺少 payload.zip，请重新构建 sts2skill.exe。",
        "Missing embedded payload.zip. Rebuild sts2skill.exe.");
    public static string DoneTitle => T("安装完成", "Installation complete");
    public static string DoneBody => T(
        "1. 启动游戏并启用 STS2 MCP 模组\n2. 角色可在 config.yaml 或各宿主 WebUI 里改（安装程序不强制选择）\n3. OpenClaw：重载 MCP；AstrBot：/sts2ai ping\n4. 命令行：sts2 doctor / sts2 ping",
        "1. Launch the game and enable STS2 MCP mod\n2. Change character in config.yaml or host WebUI (not required here)\n3. OpenClaw: reload MCP; AstrBot: /sts2ai ping\n4. CLI: sts2 doctor / sts2 ping");
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
