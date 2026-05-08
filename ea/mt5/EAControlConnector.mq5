#property strict
#property version   "0.1.0"
#property description "EA Control Center connector for MT5"

#include <Trade/Trade.mqh>

input string InpApiBaseUrl = "http://47.86.170.144";
input string InpEaToken = "change_this_ea_token";
input string InpEaId = "mt5-ea-001";
input int InpRequestTimeoutMs = 5000;
input int InpHeartbeatIntervalSec = 10;
input int InpSnapshotIntervalSec = 15;
input int InpCommandPollIntervalSec = 5;
input bool InpAllowTradingOnStart = true;

CTrade g_trade;
bool g_allow_trading = true;
datetime g_last_heartbeat = 0;
datetime g_last_snapshot = 0;
datetime g_last_command_poll = 0;

int OnInit()
{
   g_allow_trading = InpAllowTradingOnStart;
   EventSetTimer(1);
   Print("EA Control Connector initialized. ea_id=", InpEaId);
   Print("Remember to add URL in MT5: Tools -> Options -> Expert Advisors -> Allow WebRequest for listed URL");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTick()
{
   // Strategy trading logic can check g_allow_trading before opening new trades.
   if(!g_allow_trading)
      return;
}

void OnTimer()
{
   datetime now = TimeCurrent();

   if(now - g_last_heartbeat >= InpHeartbeatIntervalSec)
   {
      SendHeartbeat();
      g_last_heartbeat = now;
   }

   if(now - g_last_snapshot >= InpSnapshotIntervalSec)
   {
      SendSnapshot();
      g_last_snapshot = now;
   }

   if(now - g_last_command_poll >= InpCommandPollIntervalSec)
   {
      PollAndExecuteCommands();
      g_last_command_poll = now;
   }
}

string EscapeJson(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", "\\r");
   StringReplace(value, "\n", "\\n");
   return value;
}

bool SendApiRequest(
   string method,
   string path,
   string payload,
   int &status_code,
   string &response_body
)
{
   string url = InpApiBaseUrl + path;
   string headers = "Content-Type: application/json\r\nX-EA-Token: " + InpEaToken + "\r\n";

   uchar body[];
   uchar result[];
   string result_headers = "";

   StringToCharArray(payload, body, 0, WHOLE_ARRAY, CP_UTF8);
   if(ArraySize(body) > 0 && body[ArraySize(body) - 1] == 0)
      ArrayResize(body, ArraySize(body) - 1);

   ResetLastError();
   status_code = WebRequest(method, url, headers, InpRequestTimeoutMs, body, result, result_headers);
   if(status_code == -1)
   {
      int err = GetLastError();
      Print("WebRequest failed. path=", path, " error=", err);
      response_body = "";
      return false;
   }

   response_body = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   return true;
}

void SendHeartbeat()
{
   string terminal_name = "MT5";
   string strategy_name = MQLInfoString(MQL_PROGRAM_NAME);
   string version = MQLInfoString(MQL_PROGRAM_NAME) + "-0.1.0";
   string broker = AccountInfoString(ACCOUNT_COMPANY);
   string account = (string)AccountInfoInteger(ACCOUNT_LOGIN);

   string payload =
      "{"
      "\"ea_id\":\"" + EscapeJson(InpEaId) + "\","
      "\"account_number\":\"" + EscapeJson(account) + "\","
      "\"broker\":\"" + EscapeJson(broker) + "\","
      "\"terminal\":\"" + terminal_name + "\","
      "\"strategy_name\":\"" + EscapeJson(strategy_name) + "\","
      "\"version\":\"" + EscapeJson(version) + "\","
      "\"status\":\"online\","
      "\"allow_trading\":" + (g_allow_trading ? "true" : "false") +
      "}";

   int status = 0;
   string body = "";
   if(!SendApiRequest("POST", "/api/ea/heartbeat", payload, status, body))
      return;

   if(status < 200 || status >= 300)
      Print("Heartbeat rejected. status=", status, " body=", body);
}

string BuildPositionsJson()
{
   string result = "[";
   bool first = true;
   int total = PositionsTotal();

   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      long type = PositionGetInteger(POSITION_TYPE);
      string side = (type == POSITION_TYPE_BUY ? "buy" : "sell");
      double volume = PositionGetDouble(POSITION_VOLUME);
      double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      double current_price = PositionGetDouble(POSITION_PRICE_CURRENT);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double profit = PositionGetDouble(POSITION_PROFIT);

      string item =
         "{"
         "\"ticket\":\"" + (string)ticket + "\","
         "\"symbol\":\"" + EscapeJson(symbol) + "\","
         "\"side\":\"" + side + "\","
         "\"volume\":" + DoubleToString(volume, 2) + ","
         "\"open_price\":" + DoubleToString(open_price, _Digits) + ","
         "\"current_price\":" + DoubleToString(current_price, _Digits) + ","
         "\"sl\":" + DoubleToString(sl, _Digits) + ","
         "\"tp\":" + DoubleToString(tp, _Digits) + ","
         "\"profit\":" + DoubleToString(profit, 2) +
         "}";

      if(!first)
         result += ",";
      result += item;
      first = false;
   }

   result += "]";
   return result;
}

void SendSnapshot()
{
   string account = (string)AccountInfoInteger(ACCOUNT_LOGIN);
   string currency = AccountInfoString(ACCOUNT_CURRENCY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin = AccountInfoDouble(ACCOUNT_MARGIN);
   double free_margin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double margin_level = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   double profit = AccountInfoDouble(ACCOUNT_PROFIT);

   string payload =
      "{"
      "\"ea_id\":\"" + EscapeJson(InpEaId) + "\","
      "\"account_number\":\"" + EscapeJson(account) + "\","
      "\"currency\":\"" + EscapeJson(currency) + "\","
      "\"balance\":" + DoubleToString(balance, 2) + ","
      "\"equity\":" + DoubleToString(equity, 2) + ","
      "\"margin\":" + DoubleToString(margin, 2) + ","
      "\"free_margin\":" + DoubleToString(free_margin, 2) + ","
      "\"margin_level\":" + DoubleToString(margin_level, 2) + ","
      "\"profit\":" + DoubleToString(profit, 2) + ","
      "\"positions\":" + BuildPositionsJson() +
      "}";

   int status = 0;
   string body = "";
   if(!SendApiRequest("POST", "/api/ea/snapshot", payload, status, body))
      return;

   if(status < 200 || status >= 300)
      Print("Snapshot rejected. status=", status, " body=", body);
}

bool ExtractNextCommand(string json, int &offset, int &command_id, string &command_type)
{
   int id_key = StringFind(json, "\"id\":", offset);
   if(id_key < 0)
      return false;

   int id_start = id_key + 5;
   while(id_start < StringLen(json) && (StringGetCharacter(json, id_start) == ' ' || StringGetCharacter(json, id_start) == '\t'))
      id_start++;

   int id_end = id_start;
   while(id_end < StringLen(json))
   {
      ushort ch = (ushort)StringGetCharacter(json, id_end);
      if(ch < '0' || ch > '9')
         break;
      id_end++;
   }

   string id_text = StringSubstr(json, id_start, id_end - id_start);
   command_id = (int)StringToInteger(id_text);

   int type_key = StringFind(json, "\"command_type\":\"", id_end);
   if(type_key < 0)
      return false;
   int type_start = type_key + 16;
   int type_end = StringFind(json, "\"", type_start);
   if(type_end < 0)
      return false;

   command_type = StringSubstr(json, type_start, type_end - type_start);
   offset = type_end + 1;
   return true;
}

bool CloseAllPositions()
{
   bool ok = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(!g_trade.PositionClose(ticket))
      {
         ok = false;
         Print("Failed to close ticket=", ticket, " retcode=", g_trade.ResultRetcode());
      }
   }
   return ok;
}

void SubmitCommandResult(int command_id, string status_text, string message)
{
   string payload =
      "{"
      "\"status\":\"" + status_text + "\","
      "\"message\":\"" + EscapeJson(message) + "\""
      "}";

   int status = 0;
   string body = "";
   string path = "/api/ea/commands/" + (string)command_id + "/result";
   if(!SendApiRequest("POST", path, payload, status, body))
      return;

   if(status < 200 || status >= 300)
      Print("Submit result failed. command_id=", command_id, " status=", status, " body=", body);
}

void ExecuteCommand(int command_id, string command_type)
{
   bool success = true;
   string msg = "executed";

   if(command_type == "pause_trading")
   {
      g_allow_trading = false;
      msg = "trading paused";
   }
   else if(command_type == "resume_trading")
   {
      g_allow_trading = true;
      msg = "trading resumed";
   }
   else if(command_type == "close_all")
   {
      success = CloseAllPositions();
      msg = (success ? "all positions closed" : "close_all partially failed");
   }
   else
   {
      // For unsupported commands, return failed for now.
      success = false;
      msg = "unsupported command_type: " + command_type;
   }

   SubmitCommandResult(command_id, (success ? "success" : "failed"), msg);
}

void PollAndExecuteCommands()
{
   int status = 0;
   string body = "";
   string path = "/api/ea/commands?ea_id=" + InpEaId;

   if(!SendApiRequest("GET", path, "", status, body))
      return;
   if(status < 200 || status >= 300)
   {
      Print("Poll commands failed. status=", status, " body=", body);
      return;
   }

   int offset = 0;
   int cmd_id = 0;
   string cmd_type = "";
   while(ExtractNextCommand(body, offset, cmd_id, cmd_type))
      ExecuteCommand(cmd_id, cmd_type);
}
