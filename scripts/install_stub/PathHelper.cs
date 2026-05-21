namespace InstallLauncher;

internal static class PathHelper
{
    public static string DefaultHostPath(string host) => host switch
    {
        "astrbot" => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".astrbot", "data"),
        "openclaw" => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".openclaw"),
        "hermes" => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".hermes"),
        _ => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            "Documents", "STS2_Skills"),
    };

    public static string DefaultSkillsPath(string host, string hostPath)
    {
        if (host == "standalone")
            return hostPath;
        var parent = Path.GetDirectoryName(hostPath.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
        return Path.Combine(parent ?? hostPath, "STS2_Skills");
    }

    public static string? FindPythonForAstrBot()
    {
        var user = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        foreach (var c in new[]
        {
            Path.Combine(user, "AstrBot", "backend", "python", "python.exe"),
            Path.Combine(user, "Programs", "AstrBot", "backend", "python", "python.exe"),
        })
        {
            if (File.Exists(c))
                return c;
        }
        return FindOnPath("python") ?? FindOnPath("py");
    }

    public static string? FindOnPath(string name)
    {
        var pathEnv = Environment.GetEnvironmentVariable("PATH");
        if (string.IsNullOrEmpty(pathEnv))
            return null;
        var exts = (Environment.GetEnvironmentVariable("PATHEXT") ?? ".EXE").Split(';');
        foreach (var dir in pathEnv.Split(Path.PathSeparator))
        {
            foreach (var ext in exts)
            {
                var full = Path.Combine(dir.Trim(), name + ext);
                if (File.Exists(full))
                    return full;
            }
        }
        return null;
    }

    public static string HostPathHint(string host) => host switch
    {
        "astrbot" => I18n.HostPathHintAstrBot,
        "openclaw" => I18n.HostPathHintOpenClaw,
        "hermes" => I18n.HostPathHintHermes,
        _ => I18n.HostPathHintStandalone,
    };
}
