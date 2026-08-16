$shell = New-Object -ComObject WScript.Shell
$paths = @(
  "$env:USERPROFILE\Desktop\IRIS.lnk",
  "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\IRIS.lnk",
  "C:\Users\kwakm\Desktop\Cusor-Project\Project-IRIS-Light-main\IRIS.lnk"
)
foreach ($p in $paths) {
  $s = $shell.CreateShortcut($p)
  Write-Output ("NAME=" + [IO.Path]::GetFileName($p))
  Write-Output ("TARGET=" + $s.TargetPath)
  Write-Output ("ICON=" + $s.IconLocation)
  Write-Output ("EXISTS=" + (Test-Path $s.TargetPath))
  Write-Output "---"
}
