# Tekee kehitysversiolle Käynnistä-valikon pikakuvakkeen Windowsissa (vastaa macOS:n
# scripts/make-launcher.sh:ta): "Opintosuunnitelman muokkaaja", kuvake packaging\icon.ico.
# Pikakuvakkeella on sama AppUserModelID kuin kehitysversion prosessilla (gui/app.py), joten
# tehtäväpalkki näyttää oikean nimen ja kuvakkeen, ja kiinnitys osoittaa tähän pikakuvakkeeseen
# eikä Pythoniin. Vanhat "Opintosuunnitelmoittaja"- ja "(DEV)"-pikakuvakkeet poistetaan.
#
#   powershell -ExecutionPolicy Bypass -File scripts\make-launcher.ps1
#   ... -Destination <kansio>   pikakuvake muualle (oletus: oma Käynnistä-valikko)
#   ... -Verify                 lue pikakuvake takaisin ja tarkista nimi, kuvake ja tunnus (CI)
param(
    [string]$Destination = [Environment]::GetFolderPath("Programs"),
    [switch]$Verify
)
$ErrorActionPreference = "Stop"

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Name = "Opintosuunnitelman muokkaaja"
$Icon = Join-Path $Repo "packaging\icon.ico"
$Init = Join-Path $Repo "src\opiskelusuunnitelmoittaja\__init__.py"
$AppId = (Select-String -Path $Init -Pattern '^APP_USER_MODEL_ID = "([^"]+)"').Matches[0].Groups[1].Value
if (-not $AppId) { throw "APP_USER_MODEL_ID puuttuu tiedostosta $Init" }

# Käynnistystapa: uvw.exe PATHista (ei komentoikkunaa) tai repon Kaynnista-GUI.cmd, joka
# lisää koneen oman uv-asennuksen PATHiin (Päivitä-nappi tarvitsee uv:n).
$Uvw = Get-Command uvw.exe -ErrorAction SilentlyContinue
if ($Uvw) {
    $Target = $Uvw.Source
    $Arguments = "run --project `"$Repo`" suunnitelmoittaja-gui"
    $WindowStyle = 1
} else {
    $Target = $env:ComSpec
    $Arguments = "/c `"$(Join-Path $Repo 'Kaynnista-GUI.cmd')`""
    $WindowStyle = 7  # pienennettynä: komentoikkuna ei välähdä
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

// Pikakuvakkeen System.AppUserModel.ID IPropertyStoren kautta (WScript.Shell ei osaa sitä).
public static class LinkAppId
{
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    struct PropertyKey { public Guid FormatId; public uint PropertyId; }

    [StructLayout(LayoutKind.Explicit, Size = 24)]
    struct PropVariant { [FieldOffset(0)] public ushort Type; [FieldOffset(8)] public IntPtr Value; }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore
    {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int GetAt(uint index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropVariant value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropVariant value);
        [PreserveSig] int Commit();
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHGetPropertyStoreFromParsingName(
        string path, IntPtr bindContext, int flags, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);

    [DllImport("ole32.dll")]
    static extern int PropVariantClear(ref PropVariant value);

    const int GPS_DEFAULT = 0;
    const int GPS_READWRITE = 2;
    const ushort VT_LPWSTR = 31;

    static PropertyKey AppIdKey()
    {
        return new PropertyKey {
            FormatId = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), PropertyId = 5 };
    }

    static IPropertyStore Open(string path, int flags)
    {
        Guid iid = typeof(IPropertyStore).GUID;
        IPropertyStore store;
        SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, flags, ref iid, out store);
        return store;
    }

    public static void Set(string path, string appId)
    {
        IPropertyStore store = Open(path, GPS_READWRITE);
        try
        {
            PropertyKey key = AppIdKey();
            PropVariant value = new PropVariant {
                Type = VT_LPWSTR, Value = Marshal.StringToCoTaskMemUni(appId) };
            try
            {
                Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value));
                Marshal.ThrowExceptionForHR(store.Commit());
            }
            finally { PropVariantClear(ref value); }
        }
        finally { Marshal.ReleaseComObject(store); }
    }

    public static string Get(string path)
    {
        IPropertyStore store = Open(path, GPS_DEFAULT);
        try
        {
            PropertyKey key = AppIdKey();
            PropVariant value;
            Marshal.ThrowExceptionForHR(store.GetValue(ref key, out value));
            try { return value.Type == VT_LPWSTR ? Marshal.PtrToStringUni(value.Value) : null; }
            finally { PropVariantClear(ref value); }
        }
        finally { Marshal.ReleaseComObject(store); }
    }
}
'@

# Vanhat pikakuvakkeet pois (Käynnistä-valikko ja työpöytä)
$Old = @(
    Get-ChildItem -Path ([Environment]::GetFolderPath("Programs")) -Filter "*.lnk" -Recurse -ErrorAction SilentlyContinue
    Get-ChildItem -Path ([Environment]::GetFolderPath("Desktop")) -Filter "*.lnk" -ErrorAction SilentlyContinue
) | Where-Object {
    $_.BaseName -like "Opintosuunnitelmoittaja*" -or
    ($_.BaseName -like "*pintosuunnitelm*" -and $_.BaseName -like "*(dev)*")
}
foreach ($file in $Old) {
    Remove-Item -LiteralPath $file.FullName
    Write-Host "Poistettu vanha pikakuvake: $($file.FullName)"
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$Path = Join-Path $Destination "$Name.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Link = $Shell.CreateShortcut($Path)
$Link.TargetPath = $Target
$Link.Arguments = $Arguments
$Link.WorkingDirectory = $Repo
$Link.IconLocation = "$Icon,0"
$Link.WindowStyle = $WindowStyle
$Link.Description = $Name
$Link.Save()
[LinkAppId]::Set($Path, $AppId)
Write-Host "Pikakuvake: $Path"
Write-Host "  käynnistää: $Target $Arguments"

if ($Verify) {
    $Check = $Shell.CreateShortcut($Path)
    if ($Check.IconLocation -ne "$Icon,0") { throw "Kuvake ei tallentunut: $($Check.IconLocation)" }
    if (-not (Test-Path -LiteralPath $Icon)) { throw "Kuvaketta ei ole: $Icon" }
    $Read = [LinkAppId]::Get($Path)
    if ($Read -ne $AppId) { throw "AppUserModelID ei tallentunut: '$Read' (odotettiin '$AppId')" }
    $Item = (New-Object -ComObject Shell.Application).NameSpace($Destination).ParseName("$Name.lnk")
    Write-Host "  Shell näkee tunnuksen: $($Item.ExtendedProperty('System.AppUserModel.ID'))"
    Write-Host "OK: nimi, kuvake ja AppUserModelID ($AppId) tallentuivat"
}

Write-Host ""
Write-Host "Valmis. Poista tehtäväpalkista tai Käynnistä-valikosta vanha kiinnitys (hiiren oikea ->"
Write-Host "Irrota) ja kiinnitä uusi: Käynnistä -> '$Name' -> hiiren oikea -> Kiinnitä."
