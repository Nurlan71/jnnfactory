@echo off
setlocal enabledelayedexpansion
set "src_css=/css/src.css"

for /r "D:\Info\JNN\Soft\Jnnfactory" %%f in (*.html) do (
    set "content="
    set "has_replace=n"
    set "tempfile=%%tmp%%\%%~nf.html.tmp"
    
    <%%f (
        set "line="
        set "first=n"
        for /f "usebackq tokens=" %%l in (<%%) do (
            if "!first!"=="y" (
                set "first=n"
            ) else (
                set "first=y"
            )
            :: Check if this line has a Tilda CSS link
            echo %%l
        )
    ) > "%tempfile%"
    
    :: Simple replacement: replace any href containing tilda min.css with our src.css
    type "%tempfile%" | findstr /i "tilda.*min.css" >nul && (
        sed -i "s|href=\"/assets/tilda[^\"]*\.min\.css\"|href="%src_css%"|g" "%tempfile%"
        move /y "%tempfile%" "%%f" >nul
    ) else (
        del "%tempfile%"
    )
)
echo Done replacing CSS links