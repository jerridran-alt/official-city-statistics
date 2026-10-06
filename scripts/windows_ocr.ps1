param([string]$JobsFile,[string]$LanguageTag='zh-Hans-CN',[switch]$Probe)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
try {
 Add-Type -AssemblyName System.Runtime.WindowsRuntime
 $null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
 $null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
 $null=[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Foundation,ContentType=WindowsRuntime]
 $null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation.UniversalApiContract,ContentType=WindowsRuntime]
 $null=[Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
 $language=New-Object Windows.Globalization.Language($LanguageTag)
 $engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
 $languages=@([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object {$_.LanguageTag})
 if($Probe){@{available=($null -ne $engine);backend='windows';language=$LanguageTag;available_languages=$languages;max_dimension=[Windows.Media.Ocr.OcrEngine]::MaxImageDimension}|ConvertTo-Json -Compress;exit 0}
 if($null -eq $engine){throw "Windows OCR language unavailable: $LanguageTag. Installed: $($languages -join ', ')"}
 $awaitMethod=[System.WindowsRuntimeSystemExtensions].GetMethods()|Where-Object {$_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'}|Select-Object -First 1
 function AwaitWinRT($Operation,$ResultType){$task=$awaitMethod.MakeGenericMethod($ResultType).Invoke($null,@($Operation));$task.Wait();return $task.Result}
 $jobs=Get-Content -LiteralPath $JobsFile -Raw -Encoding UTF8|ConvertFrom-Json
 $failed=0
 foreach($job in $jobs){
  try{
   if(Test-Path -LiteralPath $job.output){continue}
   $file=AwaitWinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($job.path)) ([Windows.Storage.StorageFile])
   $stream=AwaitWinRT ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
   $decoder=AwaitWinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
   $bitmap=AwaitWinRT ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
   $result=AwaitWinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
   $lines=@($result.Lines|ForEach-Object {@{text=$_.Text;words=@($_.Words|ForEach-Object {@{text=$_.Text;x=$_.BoundingRect.X;y=$_.BoundingRect.Y;width=$_.BoundingRect.Width;height=$_.BoundingRect.Height}})}})
   @{text=$result.Text;lines=$lines;width=$bitmap.PixelWidth;height=$bitmap.PixelHeight;backend='windows';language=$LanguageTag}|ConvertTo-Json -Depth 8 -Compress|Set-Content -LiteralPath $job.output -Encoding UTF8
   $bitmap.Dispose();$stream.Dispose()
  }catch{
   $failed++
   @{error=$_.Exception.Message;backend='windows'}|ConvertTo-Json -Compress|Set-Content -LiteralPath $job.output -Encoding UTF8
  }
 }
 @{jobs=@($jobs).Count;failed=$failed}|ConvertTo-Json -Compress
 if($failed){exit 1}
} catch {@{available=$false;error=$_.Exception.Message;backend='windows'}|ConvertTo-Json -Compress;exit 1}
