using System.Reflection;

namespace InstallLauncher;

internal sealed class MainForm : Form
{
    private readonly ComboBox _langCombo = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 120 };
    private readonly Label _titleLabel = new() { AutoSize = true };
    private readonly Label _versionLabel = new() { AutoSize = true, ForeColor = Color.Gray };

    private readonly GroupBox _hostGroup = new() { Padding = new Padding(10) };
    private readonly RadioButton _rbStandalone = new() { AutoSize = true };
    private readonly RadioButton _rbHermes = new() { AutoSize = true };
    private readonly RadioButton _rbOpenClaw = new() { AutoSize = true };
    private readonly RadioButton _rbAstrBot = new() { AutoSize = true, Checked = true };

    private readonly GroupBox _pathsGroup = new() { Padding = new Padding(10) };
    private readonly Label _lblHostPath = new() { AutoSize = true };
    private readonly Label _hintHostPath = new() { AutoSize = true, ForeColor = Color.Gray, MaximumSize = new Size(520, 0) };
    private readonly TextBox _txtHostPath = new() { Width = 400, Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Top };
    private readonly Button _btnHostBrowse = new() { AutoSize = true };

    private readonly Label _lblGamePath = new() { AutoSize = true };
    private readonly Label _hintGamePath = new() { AutoSize = true, ForeColor = Color.Gray };
    private readonly TextBox _txtGamePath = new() { Width = 400, Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Top };
    private readonly Button _btnGameBrowse = new() { AutoSize = true };

    private readonly Label _lblSkillsPath = new() { AutoSize = true };
    private readonly TextBox _txtSkillsPath = new() { Width = 400, Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Top };
    private readonly Button _btnSkillsBrowse = new() { AutoSize = true };

    private readonly GroupBox _advancedGroup = new() { Padding = new Padding(10), Visible = false };
    private readonly Label _lblPython = new() { AutoSize = true };
    private readonly TextBox _txtPython = new() { Width = 400, Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Top };
    private readonly Button _btnPythonBrowse = new() { AutoSize = true };

    private readonly Button _btnAutoDetect = new() { AutoSize = true, Height = 32 };

    private readonly GroupBox _logGroup = new() { Padding = new Padding(10) };
    private readonly TextBox _txtLog = new()
    {
        Multiline = true,
        ReadOnly = true,
        ScrollBars = ScrollBars.Vertical,
        Font = new Font("Consolas", 9f),
        Dock = DockStyle.Fill,
        Height = 140,
    };
    private readonly ProgressBar _progress = new() { Style = ProgressBarStyle.Marquee, MarqueeAnimationSpeed = 30, Height = 18, Dock = DockStyle.Top };

    private readonly Label _langLabel = new() { AutoSize = true };
    private readonly Button _btnInstall = new() { AutoSize = true, Height = 36, MinimumSize = new Size(120, 36) };
    private readonly Button _btnExit = new() { AutoSize = true, Height = 36, MinimumSize = new Size(100, 36) };

    private bool _installing;

    public MainForm()
    {
        Text = "STS2_Skills";
        MinimumSize = new Size(620, 560);
        Size = new Size(640, 620);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Microsoft YaHei UI", 9f);
        _titleLabel.Font = new Font(Font.FontFamily, 12f, FontStyle.Bold);

        _langCombo.Items.AddRange(new object[] { I18n.LangZh, I18n.LangEn });
        _langCombo.SelectedIndex = 0;
        _langCombo.SelectedIndexChanged += (_, _) => OnLanguageChanged();

        _rbStandalone.CheckedChanged += (_, _) => OnHostChanged();
        _rbHermes.CheckedChanged += (_, _) => OnHostChanged();
        _rbOpenClaw.CheckedChanged += (_, _) => OnHostChanged();
        _rbAstrBot.CheckedChanged += (_, _) => OnHostChanged();

        _btnHostBrowse.Click += (_, _) => BrowseFolder(_txtHostPath, _lblHostPath.Text);
        _btnGameBrowse.Click += (_, _) => BrowseFolder(_txtGamePath, _lblGamePath.Text);
        _btnSkillsBrowse.Click += (_, _) => BrowseFolder(_txtSkillsPath, _lblSkillsPath.Text);
        _btnPythonBrowse.Click += (_, _) => BrowsePython();
        _btnAutoDetect.Click += (_, _) => RunAutoDetect(refreshHostDerived: true);
        _btnInstall.Click += async (_, _) => await RunInstallAsync();
        _btnExit.Click += (_, _) => Close();

        BuildLayout();

        OnLanguageChanged();
        Shown += (_, _) => RunAutoDetect(refreshHostDerived: true);
    }

    private void BuildLayout()
    {
        var top = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            AutoSize = true,
            ColumnCount = 3,
            Padding = new Padding(12, 12, 12, 8),
        };
        top.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        top.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        top.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        top.Controls.Add(_titleLabel, 0, 0);
        top.SetColumnSpan(_titleLabel, 2);
        top.Controls.Add(_versionLabel, 0, 1);
        top.SetColumnSpan(_versionLabel, 2);
        var langFlow = new FlowLayoutPanel { AutoSize = true, FlowDirection = FlowDirection.LeftToRight };
        langFlow.Controls.Add(_langLabel);
        langFlow.Controls.Add(_langCombo);
        top.Controls.Add(langFlow, 2, 0);
        top.SetRowSpan(langFlow, 2);

        _hostGroup.Dock = DockStyle.Top;
        _hostGroup.AutoSize = true;
        _hostGroup.AutoSizeMode = AutoSizeMode.GrowAndShrink;
        var hostFlow = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.TopDown,
            AutoSize = true,
            WrapContents = false,
        };
        hostFlow.Controls.AddRange(new Control[] { _rbStandalone, _rbHermes, _rbOpenClaw, _rbAstrBot });
        _hostGroup.Controls.Add(hostFlow);

        _pathsGroup.Dock = DockStyle.Top;
        _pathsGroup.AutoSize = true;
        _pathsGroup.AutoSizeMode = AutoSizeMode.GrowAndShrink;
        var pathsTable = new TableLayoutPanel
        {
            ColumnCount = 3,
            AutoSize = true,
            Dock = DockStyle.Top,
            Padding = new Padding(0),
        };
        pathsTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 140));
        pathsTable.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        pathsTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90));

        int row = 0;
        void AddRow(Label lbl, TextBox txt, Button btn)
        {
            pathsTable.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            pathsTable.Controls.Add(lbl, 0, row);
            pathsTable.Controls.Add(txt, 1, row);
            pathsTable.Controls.Add(btn, 2, row);
            row++;
        }
        void AddHint(Label hint)
        {
            pathsTable.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            pathsTable.Controls.Add(hint, 0, row);
            pathsTable.SetColumnSpan(hint, 3);
            row++;
        }

        AddRow(_lblHostPath, _txtHostPath, _btnHostBrowse);
        AddHint(_hintHostPath);
        AddRow(_lblGamePath, _txtGamePath, _btnGameBrowse);
        AddHint(_hintGamePath);
        AddRow(_lblSkillsPath, _txtSkillsPath, _btnSkillsBrowse);

        pathsTable.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var detectFlow = new FlowLayoutPanel { AutoSize = true, FlowDirection = FlowDirection.LeftToRight };
        detectFlow.Controls.Add(_btnAutoDetect);
        pathsTable.Controls.Add(detectFlow, 0, row);
        pathsTable.SetColumnSpan(detectFlow, 3);
        row++;

        _pathsGroup.Controls.Add(pathsTable);

        _advancedGroup.Dock = DockStyle.Top;
        _advancedGroup.AutoSize = true;
        _advancedGroup.AutoSizeMode = AutoSizeMode.GrowAndShrink;
        var advTable = new TableLayoutPanel { ColumnCount = 3, AutoSize = true, Dock = DockStyle.Top };
        advTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 140));
        advTable.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        advTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90));
        advTable.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        advTable.Controls.Add(_lblPython, 0, 0);
        advTable.Controls.Add(_txtPython, 1, 0);
        advTable.Controls.Add(_btnPythonBrowse, 2, 0);
        _advancedGroup.Controls.Add(advTable);

        _logGroup.Dock = DockStyle.Fill;
        _progress.Dock = DockStyle.Top;
        _progress.Visible = false;
        _txtLog.Dock = DockStyle.Fill;
        _logGroup.Controls.Add(_txtLog);
        _logGroup.Controls.Add(_progress);

        var bottom = new FlowLayoutPanel
        {
            Dock = DockStyle.Bottom,
            Height = 52,
            FlowDirection = FlowDirection.RightToLeft,
            Padding = new Padding(12, 8, 12, 8),
        };
        bottom.Controls.Add(_btnExit);
        bottom.Controls.Add(_btnInstall);

        var stack = new Panel { Dock = DockStyle.Fill };
        stack.Controls.Add(_logGroup);
        stack.Controls.Add(_advancedGroup);
        stack.Controls.Add(_pathsGroup);
        stack.Controls.Add(_hostGroup);
        stack.Controls.Add(top);

        Controls.Add(bottom);
        Controls.Add(stack);
    }

    private string CurrentHost()
    {
        if (_rbHermes.Checked) return "hermes";
        if (_rbOpenClaw.Checked) return "openclaw";
        if (_rbAstrBot.Checked) return "astrbot";
        return "standalone";
    }

    private void OnLanguageChanged()
    {
        I18n.Current = _langCombo.SelectedIndex == 1 ? Lang.En : Lang.Zh;
        Text = I18n.AppTitle;
        _titleLabel.Text = I18n.AppTitle;
        _versionLabel.Text = I18n.VersionLine;

        _langLabel.Text = I18n.LangLabel + ":";

        _hostGroup.Text = I18n.HostGroup;
        _rbStandalone.Text = I18n.HostStandalone;
        _rbHermes.Text = I18n.HostHermes;
        _rbOpenClaw.Text = I18n.HostOpenClaw;
        _rbAstrBot.Text = I18n.HostAstrBot;

        _pathsGroup.Text = I18n.PathsGroup;
        _lblHostPath.Text = I18n.HostPathLabel;
        _lblGamePath.Text = I18n.GamePathLabel;
        _lblSkillsPath.Text = I18n.SkillsPathLabel;
        _lblPython.Text = I18n.PythonLabel;
        _hintGamePath.Text = I18n.GamePathHint;

        _btnHostBrowse.Text = I18n.Browse;
        _btnGameBrowse.Text = I18n.Browse;
        _btnSkillsBrowse.Text = I18n.Browse;
        _btnPythonBrowse.Text = I18n.Browse;
        _btnAutoDetect.Text = I18n.AutoDetect;
        _btnInstall.Text = I18n.Install;
        _btnExit.Text = I18n.Exit;
        _logGroup.Text = I18n.LogGroup;
        _advancedGroup.Text = I18n.AdvancedGroup;

        OnHostChanged(updateHintsOnly: true);
    }

    private void OnHostChanged(bool updateHintsOnly = false)
    {
        var host = CurrentHost();
        _hintHostPath.Text = PathHelper.HostPathHint(host);
        if (!updateHintsOnly)
            RunAutoDetect(refreshHostDerived: true);
    }

    private void RunAutoDetect(bool refreshHostDerived)
    {
        PathHelper.ApplyAutoDetect(
            CurrentHost(),
            _txtHostPath,
            _txtGamePath,
            _txtSkillsPath,
            _txtPython,
            refreshHostDerived);

        var py = _txtPython.Text.Trim();
        _advancedGroup.Visible = string.IsNullOrEmpty(py) || !File.Exists(py);
    }

    private void BrowseFolder(TextBox target, string purpose)
    {
        using var dlg = new FolderBrowserDialog
        {
            Description = I18n.PickFolderTitle(purpose),
            UseDescriptionForTitle = true,
            ShowNewFolderButton = true,
        };
        var seed = target.Text.Trim();
        if (!string.IsNullOrEmpty(seed) && Directory.Exists(seed))
            dlg.InitialDirectory = seed;
        else
        {
            var host = CurrentHost();
            var fallback = PathHelper.DetectHostPath(host) ?? PathHelper.DefaultHostPath(host);
            if (Directory.Exists(fallback))
                dlg.InitialDirectory = fallback;
        }
        if (dlg.ShowDialog(this) == DialogResult.OK)
            target.Text = dlg.SelectedPath;
    }

    private void BrowsePython()
    {
        using var dlg = new OpenFileDialog
        {
            Title = I18n.PickPythonTitle,
            Filter = "Python (python.exe)|python.exe|All files|*.*",
            CheckFileExists = true,
        };
        if (dlg.ShowDialog(this) == DialogResult.OK)
            _txtPython.Text = dlg.FileName;
    }

    private void AppendLog(string line)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => AppendLog(line));
            return;
        }
        _txtLog.AppendText(line + Environment.NewLine);
    }

    private bool ValidateInputs()
    {
        var hostDir = _txtHostPath.Text.Trim();
        if (!Directory.Exists(hostDir))
        {
            MessageBox.Show(this, I18n.ErrHostPath, I18n.AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }
        var game = _txtGamePath.Text.Trim();
        if (!PathHelper.LooksLikeGameDir(game))
        {
            MessageBox.Show(this, I18n.ErrGamePath, I18n.AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }
        if (string.IsNullOrWhiteSpace(_txtSkillsPath.Text))
        {
            MessageBox.Show(this, I18n.ErrSkillsPath, I18n.AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }
        return true;
    }

    private async Task RunInstallAsync()
    {
        if (_installing)
            return;

        RunAutoDetect(refreshHostDerived: false);
        if (!ValidateInputs())
            return;

        var asm = Assembly.GetExecutingAssembly();
        var resName = asm.GetManifestResourceNames()
            .FirstOrDefault(n => n.EndsWith("payload.zip", StringComparison.OrdinalIgnoreCase));
        if (resName is null)
        {
            MessageBox.Show(this, I18n.ErrPayload, I18n.AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        _installing = true;
        _btnInstall.Enabled = false;
        _progress.Visible = true;
        _txtLog.Clear();
        AppendLog(I18n.Installing);

        var opt = new InstallOptions(
            CurrentHost(),
            _txtHostPath.Text.Trim(),
            _txtGamePath.Text.Trim(),
            _txtSkillsPath.Text.Trim(),
            _txtPython.Text.Trim());

        try
        {
            await Task.Run(() =>
            {
                using var stream = asm.GetManifestResourceStream(resName)!;
                var temp = Path.Combine(Path.GetTempPath(), "STS2_install_" + Guid.NewGuid().ToString("N"));
                try
                {
                    Directory.CreateDirectory(temp);
                    var payloadRoot = Deployer.ExtractPayloadZip(stream, temp);
                    Deployer.DeployAll(opt, payloadRoot, AppendLog);
                }
                finally
                {
                    try
                    {
                        if (Directory.Exists(temp))
                            Directory.Delete(temp, true);
                    }
                    catch { /* ignore */ }
                }
            });

            MessageBox.Show(this, I18n.DoneBody, I18n.DoneTitle, MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception ex)
        {
            AppendLog(ex.ToString());
            MessageBox.Show(this, ex.Message, I18n.FailTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            _progress.Visible = false;
            _btnInstall.Enabled = true;
            _installing = false;
        }
    }
}
