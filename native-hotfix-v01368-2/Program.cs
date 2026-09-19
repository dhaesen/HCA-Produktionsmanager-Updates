using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.IO.Ports;
using System.Linq;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using Microsoft.Win32;

namespace HcaWindowsHost
{
    internal static class Program
    {
        private const string AppId = "WerbestudioKoenigswinter.HCA.Produktionsmanager";
        private static Mutex _mutex;
        internal static readonly string LogPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "HCA Produktionsmanager", "hca-start.log");

        [DllImport("shell32.dll", SetLastError = true)]
        private static extern int SetCurrentProcessExplicitAppUserModelID([MarshalAs(UnmanagedType.LPWStr)] string appId);

        [STAThread]
        private static void Main()
        {
            try
            {
                Log("Programmstart v0.13.68.2 (Launcher-Hotfix)");
                var app = new Application { ShutdownMode = ShutdownMode.OnMainWindowClose };
                bool created;
                _mutex = new Mutex(true, "Local\\HCA-Produktionsmanager", out created);
                if (!created)
                {
                    HcaDialog.ShowStandalone("HCA Produktionsmanager", "Der HCA Produktionsmanager läuft bereits.", false, null);
                    return;
                }

                SetCurrentProcessExplicitAppUserModelID(AppId);
                app.DispatcherUnhandledException += (sender, args) =>
                {
                    Log("Oberflächenfehler: " + args.Exception);
                    HcaDialog.ShowStandalone("HCA-Fehler", args.Exception.Message, false, null);
                    args.Handled = true;
                };
                app.Run(new MainWindow());
                _mutex.ReleaseMutex();
            }
            catch (Exception ex)
            {
                Log("Schwerer Startfehler: " + ex);
                MessageBox.Show(
                    "HCA konnte nicht gestartet werden.\n\n" + ex.Message + "\n\nStartprotokoll:\n" + LogPath,
                    "HCA Produktionsmanager – Startfehler",
                    MessageBoxButton.OK,
                    MessageBoxImage.Error);
            }
        }

        internal static void Log(string message)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(LogPath));
                File.AppendAllText(LogPath, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + "  " + message + Environment.NewLine, Encoding.UTF8);
            }
            catch { }
        }
    }

    internal sealed class MainWindow : Window
    {
        private readonly WebView2 _webView;
        private readonly Grid _root;
        private readonly Grid _splash;
        private readonly TextBlock _status;
        private readonly ProgressBar _progress;
        private readonly HttpClient _http = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        private readonly JavaScriptSerializer _json = new JavaScriptSerializer();
        private readonly Dictionary<string, SerialPort> _serialPorts = new Dictionary<string, SerialPort>(StringComparer.OrdinalIgnoreCase);
        private Process _backend;
        private int _port = 8765;
        private bool _allowClose;

        public MainWindow()
        {
            Title = "HCA Produktionsmanager · Werbestudio Königswinter";
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            WindowState = WindowState.Maximized;
            MinWidth = 1100;
            MinHeight = 720;
            Background = new SolidColorBrush(Color.FromRgb(13, 14, 16));
            Icon = AppIcon.Load();

            _root = new Grid { Background = new SolidColorBrush(Color.FromRgb(13, 14, 16)) };
            _webView = new WebView2 { Visibility = Visibility.Collapsed };

            var splashBrush = new RadialGradientBrush
            {
                Center = new Point(0.5, 0.35),
                GradientOrigin = new Point(0.5, 0.35),
                RadiusX = 0.78,
                RadiusY = 0.9
            };
            splashBrush.GradientStops.Add(new GradientStop(Color.FromRgb(48, 52, 58), 0));
            splashBrush.GradientStops.Add(new GradientStop(Color.FromRgb(23, 25, 29), 0.48));
            splashBrush.GradientStops.Add(new GradientStop(Color.FromRgb(13, 14, 16), 1));

            _splash = new Grid { Background = splashBrush };
            var card = new StackPanel
            {
                Width = 520,
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center
            };
            var logoPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "assets", "logo-app.png");
            if (File.Exists(logoPath))
            {
                var bitmap = new BitmapImage();
                bitmap.BeginInit();
                bitmap.CacheOption = BitmapCacheOption.OnLoad;
                bitmap.UriSource = new Uri(logoPath, UriKind.Absolute);
                bitmap.EndInit();
                bitmap.Freeze();
                card.Children.Add(new Image
                {
                    Source = bitmap,
                    MaxWidth = 420,
                    MaxHeight = 110,
                    Stretch = Stretch.Uniform,
                    HorizontalAlignment = HorizontalAlignment.Center,
                    Margin = new Thickness(0, 0, 0, 34),
                    Effect = new DropShadowEffect { BlurRadius = 22, ShadowDepth = 8, Opacity = 0.30, Color = Colors.Black }
                });
            }
            card.Children.Add(new TextBlock
            {
                Text = "HCA wird gestartet",
                TextAlignment = TextAlignment.Center,
                FontSize = 25,
                FontWeight = FontWeights.SemiBold,
                Foreground = Brushes.White,
                Margin = new Thickness(0, 0, 0, 8)
            });
            card.Children.Add(new TextBlock
            {
                Text = "Produktionsmanager und Warenwirtschaft",
                TextAlignment = TextAlignment.Center,
                FontSize = 15,
                Foreground = new SolidColorBrush(Color.FromRgb(200, 203, 208)),
                Margin = new Thickness(0, 0, 0, 25)
            });
            _progress = new ProgressBar
            {
                Minimum = 0,
                Maximum = 100,
                Value = 5,
                Height = 8,
                Foreground = new SolidColorBrush(Color.FromRgb(239, 82, 28)),
                Background = new SolidColorBrush(Color.FromRgb(52, 55, 61)),
                BorderThickness = new Thickness(0)
            };
            card.Children.Add(_progress);
            _status = new TextBlock
            {
                Text = "Komponenten werden geladen …",
                TextAlignment = TextAlignment.Center,
                FontSize = 12,
                Foreground = new SolidColorBrush(Color.FromRgb(174, 178, 184)),
                Margin = new Thickness(0, 10, 0, 0)
            };
            card.Children.Add(_status);
            _splash.Children.Add(card);
            _root.Children.Add(_webView);
            _root.Children.Add(_splash);
            Content = _root;

            Loaded += async (sender, args) => await StartAsync();
            Closing += OnClosing;
        }

        private async Task StartAsync()
        {
            try
            {
                SetStartupProgress(14, "Startkonfiguration wird gelesen …");
                Program.Log("Startkonfiguration wird gelesen.");
                _port = ReadConfiguredPort();
                Program.Log("Lokaler Port: " + _port);
                SetStartupProgress(30, "Lokaler Dienst wird geprüft …");
                if (!await ServerAvailableAsync())
                {
                    Program.Log("Lokaler Dienst wird gestartet.");
                    SetStartupProgress(38, "Lokaler Dienst wird gestartet …");
                    StartBackend();
                }
                if (!await WaitForServerAsync(TimeSpan.FromSeconds(25)))
                    throw new InvalidOperationException("Der lokale HCA-Dienst konnte nicht gestartet werden.");

                Program.Log("Lokaler Dienst ist erreichbar.");
                SetStartupProgress(55, "WebView2 wird vorbereitet …");
                var dataFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "HCA Produktionsmanager", "WebView2");
                Directory.CreateDirectory(dataFolder);
                Program.Log("WebView2 Runtime: " + CoreWebView2Environment.GetAvailableBrowserVersionString());
                var environment = await CoreWebView2Environment.CreateAsync(null, dataFolder);
                await _webView.EnsureCoreWebView2Async(environment);
                SetStartupProgress(74, "Oberfläche wird vorbereitet …");
                await ConfigureWebViewAsync(_webView);
                await _webView.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(
                    @"(function(){var s=document.createElement('style');s.id='hca-native-splash-suppression';s.textContent='#hcaStartupSplash{display:none!important}';document.documentElement.appendChild(s);})();");

                var navigation = new TaskCompletionSource<bool>();
                CoreWebView2WebErrorStatus? navigationError = null;
                EventHandler<CoreWebView2NavigationCompletedEventArgs> completedHandler = null;
                completedHandler = (sender, args) =>
                {
                    _webView.CoreWebView2.NavigationCompleted -= completedHandler;
                    navigationError = args.IsSuccess ? (CoreWebView2WebErrorStatus?)null : args.WebErrorStatus;
                    Program.Log("WebView2 NavigationCompleted: success=" + args.IsSuccess +
                        (navigationError.HasValue ? ", status=" + navigationError.Value : string.Empty));
                    navigation.TrySetResult(args.IsSuccess);
                };
                _webView.CoreWebView2.NavigationCompleted += completedHandler;
                SetStartupProgress(88, "Arbeitsbereiche werden geladen …");
                _webView.Source = new Uri("http://127.0.0.1:" + _port + "/");
                var finished = await Task.WhenAny(navigation.Task, Task.Delay(TimeSpan.FromSeconds(120)));
                if (finished != navigation.Task)
                {
                    _webView.CoreWebView2.NavigationCompleted -= completedHandler;
                    throw new TimeoutException("Die HCA-Oberfläche hat das erweiterte Ladezeitlimit von 120 Sekunden überschritten.");
                }
                if (!await navigation.Task)
                    throw new InvalidOperationException("Die HCA-Oberfläche konnte nicht geladen werden. WebView2-Navigationsstatus: " +
                        (navigationError.HasValue ? navigationError.Value.ToString() : "unbekannt") + ".");

                SetStartupProgress(100, "HCA ist bereit.");
                await Task.Delay(120);
                _webView.Visibility = Visibility.Visible;
                _splash.Visibility = Visibility.Collapsed;
                _webView.Focus();
                Program.Log("HCA-Oberfläche wurde geöffnet.");
            }
            catch (Exception ex)
            {
                Program.Log("StartAsync fehlgeschlagen: " + ex);
                SetStartupProgress(100, "HCA konnte nicht gestartet werden.");
                HcaDialog.Show(this, "Startfehler", ex.Message + "\n\nWeitere Einzelheiten stehen im Startprotokoll:\n" + Program.LogPath, false, null);
            }
        }

        private void SetStartupProgress(double value, string message)
        {
            _progress.Value = Math.Max(_progress.Minimum, Math.Min(_progress.Maximum, value));
            _status.Text = message;
        }

        private int ReadConfiguredPort()
        {
            try
            {
                var path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "config.json");
                if (!File.Exists(path)) return 8765;
                var data = _json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path, Encoding.UTF8));
                object value;
                int port;
                return data.TryGetValue("port", out value) && int.TryParse(Convert.ToString(value), out port) ? port : 8765;
            }
            catch { return 8765; }
        }

        private void StartBackend()
        {
            var executable = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "HCA_Backend.exe");
            if (!File.Exists(executable)) throw new FileNotFoundException("HCA_Backend.exe fehlt im Installationsordner.", executable);
            _backend = Process.Start(new ProcessStartInfo
            {
                FileName = executable,
                WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            });
        }

        private async Task<bool> ServerAvailableAsync()
        {
            try
            {
                using (var response = await _http.GetAsync("http://127.0.0.1:" + _port + "/api/status"))
                    return response.IsSuccessStatusCode;
            }
            catch { return false; }
        }

        private async Task<bool> WaitForServerAsync(TimeSpan timeout)
        {
            var until = DateTime.UtcNow + timeout;
            while (DateTime.UtcNow < until)
            {
                if (await ServerAvailableAsync()) return true;
                await Task.Delay(250);
            }
            return false;
        }

        private async Task ConfigureWebViewAsync(WebView2 view)
        {
            var core = view.CoreWebView2;
            core.Settings.AreDefaultContextMenusEnabled = false;
            core.Settings.AreDevToolsEnabled = false;
            core.Settings.AreBrowserAcceleratorKeysEnabled = false;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.IsZoomControlEnabled = false;
            core.Settings.IsBuiltInErrorPageEnabled = false;
            try
            {
                core.Profile.IsPasswordAutosaveEnabled = false;
                core.Profile.IsGeneralAutofillEnabled = false;
            }
            catch { }

            var bridgePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "native-bridge.js");
            if (File.Exists(bridgePath)) await core.AddScriptToExecuteOnDocumentCreatedAsync(File.ReadAllText(bridgePath, Encoding.UTF8));

            core.ScriptDialogOpening += OnScriptDialogOpening;
            core.NewWindowRequested += OnNewWindowRequested;
            core.DownloadStarting += OnDownloadStarting;
            core.WebMessageReceived += OnWebMessageReceived;
            core.WindowCloseRequested += (sender, args) =>
            {
                var window = Window.GetWindow(view);
                if (window != null) window.Close();
            };
            core.ProcessFailed += (sender, args) => Dispatcher.Invoke(() =>
                HcaDialog.Show(this, "Darstellungsfehler", "Die Programmoberfläche wurde unerwartet beendet. HCA wird neu geladen.", false, null));
        }

        private void OnScriptDialogOpening(object sender, CoreWebView2ScriptDialogOpeningEventArgs args)
        {
            var deferral = args.GetDeferral();
            try
            {
                Program.Log("Web-Dialog abgefangen: " + args.Kind);
                var prompt = args.Kind == CoreWebView2ScriptDialogKind.Prompt;
                var confirm = args.Kind == CoreWebView2ScriptDialogKind.Confirm || prompt || args.Kind == CoreWebView2ScriptDialogKind.Beforeunload;
                string input;
                var accepted = HcaDialog.Show(this, "HCA Produktionsmanager", args.Message, confirm, prompt ? args.DefaultText : null, out input);
                if (accepted)
                {
                    if (prompt) args.ResultText = input ?? string.Empty;
                    args.Accept();
                }
            }
            finally { deferral.Complete(); }
        }

        private async void OnNewWindowRequested(object sender, CoreWebView2NewWindowRequestedEventArgs args)
        {
            var uri = args.Uri ?? string.Empty;
            Uri parsed;
            if (Uri.TryCreate(uri, UriKind.Absolute, out parsed) && parsed.Host != "127.0.0.1" && parsed.Host != "localhost" && parsed.Scheme != "about")
            {
                args.Handled = true;
                Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
                return;
            }

            var deferral = args.GetDeferral();
            try
            {
                var child = new HcaWebWindow(this, ConfigureWebViewAsync);
                await child.InitializeAsync();
                args.NewWindow = child.Core;
                args.Handled = true;
                child.Show();
            }
            finally { deferral.Complete(); }
        }

        private void OnDownloadStarting(object sender, CoreWebView2DownloadStartingEventArgs args)
        {
            var deferral = args.GetDeferral();
            try
            {
                var dialog = new SaveFileDialog
                {
                    Title = "Datei speichern",
                    FileName = Path.GetFileName(args.ResultFilePath),
                    InitialDirectory = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    AddExtension = true,
                    OverwritePrompt = true
                };
                if (dialog.ShowDialog(this) == true)
                {
                    args.ResultFilePath = dialog.FileName;
                    args.Handled = true;
                }
                else args.Cancel = true;
            }
            finally { deferral.Complete(); }
        }

        private async void OnWebMessageReceived(object sender, CoreWebView2WebMessageReceivedEventArgs args)
        {
            string id = null;
            try
            {
                var message = _json.Deserialize<Dictionary<string, object>>(args.WebMessageAsJson);
                object value;
                if (message.TryGetValue("id", out value)) id = Convert.ToString(value);
                var action = message.TryGetValue("action", out value) ? Convert.ToString(value) : string.Empty;
                var payload = message.TryGetValue("payload", out value) ? value as Dictionary<string, object> : null;
                var result = await HandleNativeActionAsync(action, payload ?? new Dictionary<string, object>());
                Reply(id, true, result, null);
            }
            catch (Exception ex) { Reply(id, false, null, ex.Message); }
        }

        private async Task<object> HandleNativeActionAsync(string action, Dictionary<string, object> payload)
        {
            switch (action)
            {
                case "serial.select":
                    var selected = SerialPortDialog.Select(this);
                    if (string.IsNullOrEmpty(selected)) throw new OperationCanceledException("Geräteauswahl abgebrochen.");
                    return new { port = selected };
                case "serial.open":
                    return OpenSerial(payload);
                case "serial.write":
                    return await WriteSerialAsync(payload);
                case "serial.read":
                    return await ReadSerialAsync(payload);
                case "serial.close":
                    return CloseSerial(payload);
                case "document.print":
                    return await PrintDocumentAsync(payload);
                default:
                    throw new InvalidOperationException("Unbekannter HCA-Systembefehl: " + action);
            }
        }

        private async Task<object> PrintDocumentAsync(Dictionary<string, object> payload)
        {
            var printer = GetString(payload, "printer");
            var data = GetString(payload, "data");
            if (string.IsNullOrWhiteSpace(printer)) throw new InvalidOperationException("Kein Dokumentendrucker ausgewählt.");
            if (string.IsNullOrWhiteSpace(data)) throw new InvalidOperationException("Das PDF enthält keine Daten.");
            var temp = Path.Combine(Path.GetTempPath(), "HCA-Dokument-" + Guid.NewGuid().ToString("N") + ".pdf");
            WebView2 printView = null;
            try
            {
                File.WriteAllBytes(temp, Convert.FromBase64String(data));
                printView = new WebView2 { Width = 1, Height = 1, Visibility = Visibility.Hidden, IsHitTestVisible = false };
                _root.Children.Add(printView);
                await printView.EnsureCoreWebView2Async(_webView.CoreWebView2.Environment);
                var loaded = new TaskCompletionSource<bool>();
                printView.CoreWebView2.NavigationCompleted += (sender, args) => loaded.TrySetResult(args.IsSuccess);
                printView.CoreWebView2.Navigate(new Uri(temp).AbsoluteUri);
                if (!await loaded.Task) throw new InvalidOperationException("Das PDF konnte für den Direktdruck nicht geladen werden.");
                var settings = printView.CoreWebView2.Environment.CreatePrintSettings();
                settings.PrinterName = printer;
                settings.ShouldPrintBackgrounds = true;
                settings.ShouldPrintHeaderAndFooter = false;
                var status = await printView.CoreWebView2.PrintAsync(settings);
                if (status != CoreWebView2PrintStatus.Succeeded) throw new InvalidOperationException("Windows meldet beim Direktdruck: " + status);
                return new { printed = true, printer = printer };
            }
            finally
            {
                if (printView != null) { _root.Children.Remove(printView); printView.Dispose(); }
                try { File.Delete(temp); } catch { }
            }
        }

        private object OpenSerial(Dictionary<string, object> payload)
        {
            var name = GetString(payload, "port");
            if (string.IsNullOrWhiteSpace(name)) throw new InvalidOperationException("Kein COM-Port ausgewählt.");
            CloseSerialPort(name);
            var serial = new SerialPort(name)
            {
                BaudRate = GetInt(payload, "baudRate", 115200),
                DataBits = GetInt(payload, "dataBits", 8),
                StopBits = GetInt(payload, "stopBits", 1) == 2 ? StopBits.Two : StopBits.One,
                Parity = ParseParity(GetString(payload, "parity")),
                Handshake = ParseHandshake(GetString(payload, "flowControl")),
                ReadTimeout = 120,
                WriteTimeout = 5000,
                DtrEnable = true,
                RtsEnable = false
            };
            serial.Open();
            _serialPorts[name] = serial;
            return new { opened = true };
        }

        private async Task<object> WriteSerialAsync(Dictionary<string, object> payload)
        {
            var serial = RequireSerial(GetString(payload, "port"));
            var bytes = Convert.FromBase64String(GetString(payload, "data"));
            await Task.Run(() => serial.Write(bytes, 0, bytes.Length));
            return new { bytes = bytes.Length };
        }

        private async Task<object> ReadSerialAsync(Dictionary<string, object> payload)
        {
            var serial = RequireSerial(GetString(payload, "port"));
            return await Task.Run<object>(() =>
            {
                var available = serial.BytesToRead;
                if (available <= 0)
                {
                    Thread.Sleep(75);
                    available = serial.BytesToRead;
                }
                if (available <= 0) return new { data = string.Empty, done = false };
                var buffer = new byte[Math.Min(available, 16384)];
                var count = serial.Read(buffer, 0, buffer.Length);
                return new { data = Convert.ToBase64String(buffer, 0, count), done = false };
            });
        }

        private object CloseSerial(Dictionary<string, object> payload)
        {
            CloseSerialPort(GetString(payload, "port"));
            return new { closed = true };
        }

        private void CloseSerialPort(string name)
        {
            SerialPort serial;
            if (string.IsNullOrEmpty(name) || !_serialPorts.TryGetValue(name, out serial)) return;
            _serialPorts.Remove(name);
            try { if (serial.IsOpen) serial.Close(); } catch { }
            serial.Dispose();
        }

        private SerialPort RequireSerial(string name)
        {
            SerialPort serial;
            if (!_serialPorts.TryGetValue(name, out serial) || !serial.IsOpen)
                throw new InvalidOperationException("Der COM-Port " + name + " ist nicht geöffnet.");
            return serial;
        }

        private static string GetString(Dictionary<string, object> values, string key)
        {
            object value;
            return values.TryGetValue(key, out value) ? Convert.ToString(value) : string.Empty;
        }

        private static int GetInt(Dictionary<string, object> values, string key, int fallback)
        {
            int result;
            return int.TryParse(GetString(values, key), out result) ? result : fallback;
        }

        private static Parity ParseParity(string value)
        {
            switch ((value ?? string.Empty).ToLowerInvariant())
            {
                case "even": return Parity.Even;
                case "odd": return Parity.Odd;
                case "mark": return Parity.Mark;
                case "space": return Parity.Space;
                default: return Parity.None;
            }
        }

        private static Handshake ParseHandshake(string value)
        {
            return string.Equals(value, "hardware", StringComparison.OrdinalIgnoreCase)
                ? Handshake.RequestToSend
                : string.Equals(value, "software", StringComparison.OrdinalIgnoreCase)
                    ? Handshake.XOnXOff
                    : Handshake.None;
        }

        private void Reply(string id, bool ok, object result, string error)
        {
            if (_webView.CoreWebView2 == null) return;
            _webView.CoreWebView2.PostWebMessageAsJson(_json.Serialize(new { type = "hca-native-result", id, ok, result, error }));
        }

        private async void OnClosing(object sender, CancelEventArgs args)
        {
            if (_allowClose) return;
            args.Cancel = true;
            _allowClose = true;
            foreach (var name in _serialPorts.Keys.ToArray()) CloseSerialPort(name);
            try { await _http.PostAsync("http://127.0.0.1:" + _port + "/api/shutdown", new StringContent(string.Empty)); } catch { }
            if (_backend != null && !_backend.HasExited)
            {
                if (!_backend.WaitForExit(1500))
                {
                    try { _backend.Kill(); } catch { }
                }
            }
            Close();
        }
    }

    internal sealed class HcaWebWindow : Window
    {
        private readonly WebView2 _view = new WebView2();
        private readonly Func<WebView2, Task> _configure;
        public CoreWebView2 Core { get { return _view.CoreWebView2; } }

        public HcaWebWindow(Window owner, Func<WebView2, Task> configure)
        {
            Owner = owner;
            Title = "HCA Dokument";
            Width = 1100;
            Height = 800;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;
            Icon = owner.Icon;
            Content = _view;
            _configure = configure;
        }

        public async Task InitializeAsync()
        {
            await _view.EnsureCoreWebView2Async();
            await _configure(_view);
        }
    }

    internal sealed class SerialPortDialog : Window
    {
        private readonly ListBox _ports;
        public string SelectedPort { get; private set; }

        private SerialPortDialog(Window owner)
        {
            Owner = owner;
            Title = "HCA · COM-Port auswählen";
            Width = 430;
            Height = 390;
            ResizeMode = ResizeMode.NoResize;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;
            Background = Brushes.White;
            Icon = owner.Icon;

            var root = new DockPanel { Margin = new Thickness(24) };
            var title = new TextBlock { Text = "Gerät auswählen", FontSize = 24, FontWeight = FontWeights.Bold, Margin = new Thickness(0, 0, 0, 8) };
            DockPanel.SetDock(title, Dock.Top);
            root.Children.Add(title);
            var help = new TextBlock { Text = "Wähle den COM-Port des angeschlossenen Geräts.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 16), Foreground = Brushes.DimGray };
            DockPanel.SetDock(help, Dock.Top);
            root.Children.Add(help);
            var actions = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 16, 0, 0) };
            var cancel = HcaDialog.Button("Abbrechen", false);
            var ok = HcaDialog.Button("Auswählen", true);
            cancel.Click += (sender, args) => { DialogResult = false; };
            ok.Click += (sender, args) =>
            {
                SelectedPort = _ports.SelectedItem as string;
                if (!string.IsNullOrEmpty(SelectedPort)) DialogResult = true;
            };
            actions.Children.Add(cancel);
            actions.Children.Add(ok);
            DockPanel.SetDock(actions, Dock.Bottom);
            root.Children.Add(actions);
            _ports = new ListBox { FontSize = 18, Padding = new Thickness(8), ItemsSource = SerialPort.GetPortNames().OrderBy(x => x).ToArray() };
            if (_ports.Items.Count > 0) _ports.SelectedIndex = 0;
            _ports.MouseDoubleClick += (sender, args) => { if (_ports.SelectedItem != null) { SelectedPort = (string)_ports.SelectedItem; DialogResult = true; } };
            root.Children.Add(_ports);
            Content = root;
        }

        public static string Select(Window owner)
        {
            var dialog = new SerialPortDialog(owner);
            return dialog.ShowDialog() == true ? dialog.SelectedPort : null;
        }
    }

    internal sealed class HcaDialog : Window
    {
        private readonly TextBox _input;
        public bool Accepted { get; private set; }
        public string InputText { get { return _input == null ? null : _input.Text; } }

        private HcaDialog(Window owner, string title, string message, bool confirm, string defaultText)
        {
            Owner = owner;
            Title = "HCA Produktionsmanager";
            Width = 590;
            SizeToContent = SizeToContent.Height;
            MaxHeight = 760;
            ResizeMode = ResizeMode.NoResize;
            WindowStartupLocation = owner == null ? WindowStartupLocation.CenterScreen : WindowStartupLocation.CenterOwner;
            WindowStyle = WindowStyle.None;
            AllowsTransparency = true;
            Background = Brushes.Transparent;
            ShowInTaskbar = false;
            Icon = owner == null ? AppIcon.Load() : owner.Icon;

            var frame = new Border
            {
                Background = Brushes.White,
                BorderBrush = new SolidColorBrush(Color.FromRgb(196, 196, 190)),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(18),
                ClipToBounds = true,
                Effect = new DropShadowEffect { BlurRadius = 28, ShadowDepth = 8, Opacity = .28, Color = Colors.Black }
            };
            var layout = new Grid();
            layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var header = new Grid { Background = new SolidColorBrush(Color.FromRgb(31, 31, 29)), Height = 76 };
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            FrameworkElement brand;
            var brandSource = AppIcon.LoadAsset("logo-app.png");
            if (brandSource != null) brand = new Image { Source = brandSource, Width = 174, Height = 48, Stretch = Stretch.Uniform, Margin = new Thickness(22, 0, 18, 0), VerticalAlignment = VerticalAlignment.Center };
            else
            {
                var mark = new Border { Width = 42, Height = 42, CornerRadius = new CornerRadius(10), Background = new SolidColorBrush(Color.FromRgb(239, 82, 0)), Margin = new Thickness(22, 0, 14, 0), VerticalAlignment = VerticalAlignment.Center };
                mark.Child = new TextBlock { Text = "HCA", Foreground = Brushes.White, FontWeight = FontWeights.Bold, FontSize = 12, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
                brand = mark;
            }
            Grid.SetColumn(brand, 0); header.Children.Add(brand);
            var headerText = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            headerText.Children.Add(new TextBlock { Text = "WERBESTUDIO KÖNIGSWINTER", Foreground = new SolidColorBrush(Color.FromRgb(255, 91, 20)), FontSize = 11, FontWeight = FontWeights.Bold });
            headerText.Children.Add(new TextBlock { Text = title, Foreground = Brushes.White, FontSize = 18, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 3, 0, 0) });
            Grid.SetColumn(headerText, 1); header.Children.Add(headerText);
            header.MouseLeftButtonDown += (sender, args) => { if (args.ButtonState == System.Windows.Input.MouseButtonState.Pressed) DragMove(); };
            Grid.SetRow(header, 0); layout.Children.Add(header);

            var root = new StackPanel { Margin = new Thickness(28, 24, 28, 25) };
            root.Children.Add(new TextBlock { Text = message ?? string.Empty, TextWrapping = TextWrapping.Wrap, FontSize = 16, LineHeight = 25, Foreground = new SolidColorBrush(Color.FromRgb(65, 65, 62)), MaxHeight = 430 });
            if (defaultText != null)
            {
                _input = new TextBox { Text = defaultText, FontSize = 16, Padding = new Thickness(12), Margin = new Thickness(0, 18, 0, 0), BorderBrush = new SolidColorBrush(Color.FromRgb(190, 190, 184)), BorderThickness = new Thickness(1) };
                root.Children.Add(_input);
            }
            var actions = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 22, 0, 0) };
            if (confirm)
            {
                var cancel = Button("Abbrechen", false);
                cancel.Click += (sender, args) => { Accepted = false; DialogResult = false; };
                actions.Children.Add(cancel);
            }
            var okay = Button(confirm ? "Bestätigen" : "OK", true);
            okay.Click += (sender, args) => { Accepted = true; DialogResult = true; };
            actions.Children.Add(okay);
            root.Children.Add(actions);
            Grid.SetRow(root, 1); layout.Children.Add(root);frame.Child = layout;Content = frame;
            Loaded += (sender, args) => { if (_input != null) { _input.Focus(); _input.SelectAll(); } else okay.Focus(); };
        }

        public static System.Windows.Controls.Button Button(string text, bool primary)
        {
            var button = new System.Windows.Controls.Button
            {
                Content = text,
                MinWidth = 112,
                Height = 42,
                Margin = new Thickness(8, 0, 0, 0),
                Padding = new Thickness(14, 0, 14, 0),
                FontSize = 15,
                FontWeight = FontWeights.SemiBold,
                Foreground = primary ? Brushes.White : new SolidColorBrush(Color.FromRgb(45, 45, 43)),
                Background = primary ? new SolidColorBrush(Color.FromRgb(239, 82, 0)) : new SolidColorBrush(Color.FromRgb(235, 235, 232)),
                BorderThickness = new Thickness(0)
            };
            var border = new FrameworkElementFactory(typeof(Border));
            border.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(System.Windows.Controls.Button.BackgroundProperty));
            border.SetValue(Border.CornerRadiusProperty, new CornerRadius(9));
            var content = new FrameworkElementFactory(typeof(ContentPresenter));
            content.SetValue(ContentPresenter.HorizontalAlignmentProperty, HorizontalAlignment.Center);
            content.SetValue(ContentPresenter.VerticalAlignmentProperty, VerticalAlignment.Center);
            border.AppendChild(content);
            button.Template = new ControlTemplate(typeof(System.Windows.Controls.Button)) { VisualTree = border };
            return button;
        }

        public static bool Show(Window owner, string title, string message, bool confirm, string defaultText, out string input)
        {
            var dialog = new HcaDialog(owner, title, message, confirm, defaultText);
            dialog.ShowDialog();
            input = dialog.InputText;
            return dialog.Accepted;
        }

        public static bool Show(Window owner, string title, string message, bool confirm, string defaultText)
        {
            string ignored;
            return Show(owner, title, message, confirm, defaultText, out ignored);
        }

        public static void ShowStandalone(string title, string message, bool confirm, string defaultText)
        {
            var app = Application.Current ?? new Application();
            var dialog = new HcaDialog(null, title, message, confirm, defaultText);
            dialog.ShowDialog();
        }
    }

    internal static class AppIcon
    {
        public static ImageSource LoadAsset(string fileName)
        {
            try
            {
                var path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "assets", fileName);
                if (!File.Exists(path)) return null;
                var bitmap = new BitmapImage();
                bitmap.BeginInit();
                bitmap.CacheOption = BitmapCacheOption.OnLoad;
                bitmap.UriSource = new Uri(path, UriKind.Absolute);
                bitmap.EndInit();
                if (bitmap.CanFreeze) bitmap.Freeze();
                return bitmap;
            }
            catch { return null; }
        }

        public static ImageSource Load()
        {
            try
            {
                var path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "assets", "HCA.ico");
                if (!File.Exists(path)) return null;
                using (var stream = File.OpenRead(path))
                {
                    var frame = BitmapFrame.Create(stream, BitmapCreateOptions.PreservePixelFormat, BitmapCacheOption.OnLoad);
                    if (frame.CanFreeze) frame.Freeze();
                    return frame;
                }
            }
            catch (Exception ex)
            {
                Program.Log("Fenstersymbol konnte nicht geladen werden: " + ex.Message);
                return null;
            }
        }
    }
}
