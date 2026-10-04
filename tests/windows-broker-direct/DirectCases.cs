// Finite synthetic cases and clean environment. No arbitrary command input.
using System;
using System.IO;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;

public static partial class BrokerDirectLauncher {
    static void SafePath(string path) {
        if(!Path.IsPathRooted(path) || path.IndexOfAny(new char[]{'"','\'','\0','\r','\n','%','!','&','|','<','>','^'})>=0)
            throw new ArgumentException("fixed fixture path contains unsupported syntax");
    }
    static string HashFile(string path) {
        using(var sha=SHA256.Create()) using(var file=File.OpenRead(path))
            return BitConverter.ToString(sha.ComputeHash(file)).Replace("-","").ToLowerInvariant();
    }
    static string EnvironmentBlock(string workspace,string code) {
        string windows=Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        SafePath(windows);if(!Directory.Exists(windows)) throw new InvalidOperationException("Windows root unavailable");
        var values=new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase) {
            {"APPDATA",workspace},{"GIT_CONFIG_GLOBAL",Path.Combine(workspace,"empty.gitconfig")},{"GIT_CONFIG_NOSYSTEM","1"},
            {"GIT_TERMINAL_PROMPT","0"},{"HOME",workspace},{"LOCALAPPDATA",workspace},
            {"npm_config_cache",Path.Combine(workspace,"npm-cache")},{"npm_config_globalconfig",Path.Combine(workspace,"empty-global.npmrc")},
            {"npm_config_userconfig",Path.Combine(workspace,"empty.npmrc")},
            {"Path",Path.Combine(code,"runtime")+";"+Path.Combine(windows,"System32")+";"+windows},
            {"POWERSHELL_TELEMETRY_OPTOUT","1"},{"POWERSHELL_UPDATECHECK","Off"},{"PYTHONIOENCODING","utf-8"},
            {"PYTHONLEGACYWINDOWSSTDIO","0"},{"PYTHONUTF8","1"},{"SystemDrive",Path.GetPathRoot(windows).TrimEnd('\\')},
            {"SystemRoot",windows},{"TEMP",workspace},{"TMP",workspace},{"USERPROFILE",workspace},{"windir",windows}
        };
        var text=new StringBuilder();foreach(var pair in values) text.Append(pair.Key+"="+pair.Value+"\0");
        return text.Append('\0').ToString();
    }
    static string FixedCommand(string kind,string code,string workspace,string outside,int port,out string exe) {
        foreach(string path in new string[]{code,workspace,outside}) SafePath(path);
        string mutation=Path.Combine(workspace,"mutation.txt"),read=Path.Combine(outside,"canary.txt"),write=Path.Combine(outside,"probe-write.txt");
        string receipt=Path.Combine(workspace,"runtime-canary.txt");
        if(kind=="reference") {
            exe=Path.Combine(code,"fixture.exe");return Quote(exe)+" sandbox "+Quote(workspace)+" "+Quote(outside)+" 127.0.0.1:"+port;
        }
        if(kind=="node") {
            exe=Path.Combine(code,"runtime\\node.exe");
            string script="const fs=require('fs');fs.writeFileSync('script-entry.txt','runtime-entered');fs.writeFileSync('mutation.txt','runtime-ok');console.log(fs.readFileSync('mutation.txt','utf8'));"+
                "let r='unexpected_success',w='unexpected_success';try{fs.readFileSync('"+read.Replace("\\","\\\\")+"')}catch(e){r=e.code}"+
                "try{fs.writeFileSync('"+write.Replace("\\","\\\\")+"','runtime-escape')}catch(e){w=e.code}"+
                "fs.writeFileSync('runtime-canary.txt','read='+r+'\\nwrite='+w+'\\n');if(r!=='EACCES'||w!=='EACCES')process.exitCode=2;";
            return Quote(exe)+" -e "+Quote(script);
        }
        if(kind=="cmd") {
            exe=Path.Combine(code,"cmd.exe");
            // cmd errorlevel is not a raw Win32 error. Preserve this observation as inconclusive.
            File.WriteAllText(Path.Combine(workspace,"direct.cmd"),"@echo off\r\necho runtime-entered>script-entry.txt\r\necho runtime-ok>mutation.txt\r\ntype mutation.txt\r\n"+
                "type \""+read+"\" >outside-read.txt\r\necho read_errorlevel=%errorlevel%>runtime-canary.txt\r\n"+
                "echo runtime-escape>\""+write+"\"\r\necho write_errorlevel=%errorlevel%>>runtime-canary.txt\r\nexit /b 0\r\n",Encoding.ASCII);
            return Quote(exe)+" /d /q /c direct.cmd";
        }
        if(kind=="powershell" || kind=="pwsh") {
            exe=Path.Combine(code,kind=="pwsh"?"runtime\\pwsh.exe":"runtime\\powershell.exe");
            string script="$ErrorActionPreference='Stop';[IO.File]::WriteAllText('"+Path.Combine(workspace,"script-entry.txt")+"','runtime-entered');[IO.File]::WriteAllText('"+mutation+"','runtime-ok');"+
                "[Console]::WriteLine([IO.File]::ReadAllText('"+mutation+"'));$r=0;$w=0;$rt='success';$wt='success';"+
                "try{[IO.File]::ReadAllText('"+read+"')|Out-Null}catch{$e=$_.Exception.GetBaseException();$r=$e.HResult;$rt=$e.GetType().FullName};"+
                "try{[IO.File]::WriteAllText('"+write+"','runtime-escape')}catch{$e=$_.Exception.GetBaseException();$w=$e.HResult;$wt=$e.GetType().FullName};"+
                "[IO.File]::WriteAllText('"+receipt+"',('read_type='+$rt+[char]10+'read_hresult='+$r+[char]10+'write_type='+$wt+[char]10+'write_hresult='+$w+[char]10));"+
                "if($r -ne -2147024891 -or $w -ne -2147024891 -or $rt -ne 'System.UnauthorizedAccessException' -or $wt -ne 'System.UnauthorizedAccessException'){exit 2}";
            return Quote(exe)+" -NoLogo -NoProfile -NonInteractive -Command "+Quote(script);
        }
        throw new ArgumentException("unknown fixed direct case");
    }
}
