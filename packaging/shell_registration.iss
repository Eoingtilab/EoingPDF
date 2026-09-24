{ Included in the production installer and its isolated integration test. }
var
  ShellRegistrationFailed: Boolean;

function ShellRegistrationSucceeded: Boolean;
begin
  Result := not ShellRegistrationFailed;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  ReportPath: String;
  Report: AnsiString;
begin
  if CurStep = ssPostInstall then
  begin
    ReportPath := ExpandConstant('{tmp}\eoing-shell-result.json');
    ShellRegistrationFailed := True;
    if Exec(ExpandConstant('{app}\EoingPDF.exe'),
      '--register-shell --shell-result "' + ReportPath + '"',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      ShellRegistrationFailed := ResultCode <> 0;
      Log(Format('EoingPDF shell registration exit code: %d', [ResultCode]));
    end
    else
      Log(Format('Could not start EoingPDF shell registration: %d', [ResultCode]));
    if LoadStringFromFile(ReportPath, Report) then
      Log(String(Report));
    if ShellRegistrationFailed then
    begin
      Log('EoingPDF installation is incomplete: shell registration failed. Setup exit code 20.');
      if not WizardSilent then
        MsgBox('파일은 설치했지만 우클릭 메뉴와 PDF 연결을 등록하지 못했습니다.' + #13#10 +
          '사용자 계정 정책을 확인한 뒤 설치를 다시 실행해 주세요.', mbError, MB_OK);
    end;
  end;
end;

function GetCustomSetupExitCode: Integer;
begin
  if ShellRegistrationFailed then
    Result := 20
  else
    Result := 0;
end;
