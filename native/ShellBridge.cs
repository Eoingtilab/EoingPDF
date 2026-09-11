// Tiny out-of-process IDropTarget server. Explorer passes the complete selection.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
using System.Windows.Forms;

[ComImport, Guid("00000122-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IDropTarget {
    [PreserveSig] int DragEnter([MarshalAs(UnmanagedType.Interface)] System.Runtime.InteropServices.ComTypes.IDataObject data, uint keys, long point, ref uint effect);
    [PreserveSig] int DragOver(uint keys, long point, ref uint effect);
    [PreserveSig] int DragLeave();
    [PreserveSig] int Drop([MarshalAs(UnmanagedType.Interface)] System.Runtime.InteropServices.ComTypes.IDataObject data, uint keys, long point, ref uint effect);
}
[ComVisible(true), Guid("00000001-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IClassFactory {
    [PreserveSig] int CreateInstance(IntPtr outer, ref Guid iid, out IntPtr instance);
    [PreserveSig] int LockServer(bool locked);
}
[ComVisible(true), ClassInterface(ClassInterfaceType.None)]
public class DropTarget : IDropTarget {
    public static string Action;
    public static bool SelfTest;
    public static string[] Received;
    public int DragEnter(System.Runtime.InteropServices.ComTypes.IDataObject data, uint keys, long point, ref uint effect) { effect = 1; return 0; }
    public int DragOver(uint keys, long point, ref uint effect) { effect = 1; return 0; }
    public int DragLeave() { return 0; }
    public int Drop(System.Runtime.InteropServices.ComTypes.IDataObject data, uint keys, long point, ref uint effect) {
        try {
            var format = new FORMATETC { cfFormat = 15, dwAspect = DVASPECT.DVASPECT_CONTENT, lindex = -1, tymed = TYMED.TYMED_HGLOBAL };
            STGMEDIUM medium;
            data.GetData(ref format, out medium);
            var files = new List<string>();
            try {
                uint count = Native.DragQueryFile(medium.unionmember, 0xffffffff, null, 0);
                for (uint i = 0; i < count; i++) {
                    uint size = Native.DragQueryFile(medium.unionmember, i, null, 0);
                    var buffer = new StringBuilder((int)size + 1);
                    Native.DragQueryFile(medium.unionmember, i, buffer, size + 1);
                    files.Add(buffer.ToString());
                }
            } finally { Native.ReleaseStgMedium(ref medium); }
            if (files.Count == 0) return unchecked((int)0x80070057);
            Received = files.ToArray();
            if (!SelfTest) {
                string root = AppDomain.CurrentDomain.BaseDirectory;
                string queue = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "EoingPDF", "queue");
                Directory.CreateDirectory(queue);
                string manifest = Path.Combine(queue, Guid.NewGuid().ToString("N") + ".files");
                // Newlines cannot occur in Windows file names. UTF-8 preserves Korean paths.
                File.WriteAllLines(manifest, files, new UTF8Encoding(false));
                string exe = Path.Combine(root, "EoingPDF.exe");
                var start = new ProcessStartInfo(exe, "--quick " + Action + " --manifest \"" + manifest + "\"");
                start.UseShellExecute = false;
                start.CreateNoWindow = true;
                Process.Start(start);
            }
            effect = 1;
            return 0;
        } catch (Exception error) {
            if (!SelfTest) MessageBox.Show("어잉PDF를 시작하지 못했습니다. 포터블 폴더 위치를 확인하고 우클릭 메뉴를 다시 등록해 주세요.\n" + error.Message);
            return Marshal.GetHRForException(error);
        } finally {
            if (!SelfTest) Program.ExitSoon();
        }
    }
}
[ComVisible(true), ClassInterface(ClassInterfaceType.None)]
public class Factory : IClassFactory {
    public int CreateInstance(IntPtr outer, ref Guid iid, out IntPtr instance) {
        instance = IntPtr.Zero;
        if (outer != IntPtr.Zero) return unchecked((int)0x80040110);
        IntPtr unknown = Marshal.GetIUnknownForObject(new DropTarget());
        try { return Marshal.QueryInterface(unknown, ref iid, out instance); }
        finally { Marshal.Release(unknown); }
    }
    public int LockServer(bool locked) { return 0; }
}
public static class Native {
    [DllImport("ole32.dll")] public static extern int CoRegisterClassObject(ref Guid clsid, [MarshalAs(UnmanagedType.Interface)] IClassFactory factory, uint context, uint flags, out uint cookie);
    [DllImport("ole32.dll")] public static extern int CoRevokeClassObject(uint cookie);
    [DllImport("ole32.dll")] public static extern int OleInitialize(IntPtr reserved);
    [DllImport("ole32.dll")] public static extern void OleUninitialize();
    [DllImport("ole32.dll")] public static extern void ReleaseStgMedium(ref STGMEDIUM medium);
    [DllImport("shell32.dll", CharSet=CharSet.Unicode)] public static extern uint DragQueryFile(IntPtr drop, uint index, StringBuilder file, uint count);
}
public class Program {
    static System.Windows.Forms.Timer exitTimer;
    public static void ExitSoon() {
        exitTimer = new System.Windows.Forms.Timer();
        exitTimer.Interval = 1500;
        exitTimer.Tick += delegate { Application.ExitThread(); };
        exitTimer.Start();
    }
    [STAThread]
    public static int Main(string[] args) {
        Native.OleInitialize(IntPtr.Zero);
        try {
            if (args.Length >= 3 && args[0] == "--integration-test") {
                Guid testClsid = new Guid(args[1]);
                var paths = new string[args.Length - 2];
                Array.Copy(args, 2, paths, 0, paths.Length);
                object server = Activator.CreateInstance(Type.GetTypeFromCLSID(testClsid));
                var target = (IDropTarget)server;
                var data = new System.Windows.Forms.DataObject(DataFormats.FileDrop, paths);
                uint effect = 1;
                int result = target.Drop((System.Runtime.InteropServices.ComTypes.IDataObject)data, 0, 0, ref effect);
                Marshal.FinalReleaseComObject(server);
                return result;
            }
            if (args.Length > 0 && args[0] == "--self-test") {
                DropTarget.SelfTest = true;
                var paths = new string[] { @"C:\한글 폴더\문서 1.pdf", @"C:\문서\둘 & 셋.docx", @"D:\이미지.png" };
                var data = new System.Windows.Forms.DataObject(DataFormats.FileDrop, paths);
                uint effect = 1;
                int result = new DropTarget().Drop((System.Runtime.InteropServices.ComTypes.IDataObject)data, 0, 0, ref effect);
                bool ok = result == 0 && DropTarget.Received.Length == paths.Length;
                for (int i = 0; ok && i < paths.Length; i++) ok = paths[i] == DropTarget.Received[i];
                if (args.Length > 1) File.WriteAllText(args[1], ok ? "PASS: complete Unicode selection" : "FAIL");
                return ok ? 0 : 1;
            }
            string action = args.Length > 0 ? args[0] : "merge";
            var ids = new Dictionary<string, string> {
                {"merge", "7EA027AD-393A-49DE-9F95-7DA2CB0D9481"},
                {"convert", "7EA027AD-393A-49DE-9F95-7DA2CB0D9482"},
                {"summary", "7EA027AD-393A-49DE-9F95-7DA2CB0D9483"}
            };
            if (!ids.ContainsKey(action)) return 2;
            DropTarget.Action = action;
            Guid clsid = new Guid(ids[action]);
            uint cookie;
            var factory = new Factory();
            int hr = Native.CoRegisterClassObject(ref clsid, factory, 4, 1, out cookie);
            if (hr < 0) return hr;
            var timeout = new System.Windows.Forms.Timer();
            timeout.Interval = 30000;
            timeout.Tick += delegate { Application.ExitThread(); };
            timeout.Start();
            Application.Run();
            Native.CoRevokeClassObject(cookie);
            GC.KeepAlive(factory);
            return 0;
        } catch (Exception error) {
            Console.Error.WriteLine(error.ToString());
            File.WriteAllText(Path.Combine(Path.GetTempPath(), "EoingPDF-shell-error.log"), error.ToString());
            if (args.Length == 0 || !args[0].Contains("test"))
                MessageBox.Show("어잉PDF 우클릭 작업을 시작하지 못했습니다. 메뉴를 다시 등록해 주세요.", "어잉PDF");
            return 1;
        } finally { Native.OleUninitialize(); }
    }
}
