#property strict
#property version   "0.2.0"
#property description "EA Control Center connector for MT5"

#include <Trade/Trade.mqh>

input string InpApiBaseUrl = "http://127.0.0.1:8000";
input string InpEaToken = "ea123456";
input string InpEaId = ""; // Leave empty to auto-generate: mt5-{account}-{server}-{magic}
input int InpRequestTimeoutMs = 5000;
input int InpHeartbeatIntervalSec = 5;
input int InpSnapshotIntervalSec = 10;
input int InpCommandPollIntervalSec = 2;
input int InpTradeDeviationPoints = 20;
input long InpMagicNumber = 20260509;
input bool InpAllowTradingOnStart = true;

CTrade g_trade;
bool g_allow_trading = true;
int g_heartbeat_interval_sec = 10;
int g_snapshot_interval_sec = 15;
int g_command_poll_interval_sec = 5;
datetime g_last_heartbeat = 0;
datetime g_last_snapshot = 0;
datetime g_last_command_poll = 0;
string g_effective_ea_id = "";

void LogMessage(string message)
{
   Print("[EAControlConnector] ", message);
}

string EscapeJson(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", "\\r");
   StringReplace(value, "\n", "\\n");
   return value;
}

string SlugPart(string value, string fallback)
{
   string result = value;
   StringToLower(result);
   StringTrimLeft(result);
   StringTrimRight(result);
   string output = "";
   bool last_dash = false;
   for(int i = 0; i < StringLen(result); i++)
   {
      ushort ch = StringGetCharacter(result, i);
      bool ok = (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '.' || ch == '_' || ch == ':' || ch == '-';
      if(ok)
      {
         output += ShortToString(ch);
         last_dash = (ch == '-');
      }
      else if(!last_dash && StringLen(output) > 0)
      {
         output += "-";
         last_dash = true;
      }
   }
   while(StringLen(output) > 0 && StringSubstr(output, StringLen(output) - 1, 1) == "-")
      output = StringSubstr(output, 0, StringLen(output) - 1);
   if(StringLen(output) == 0)
      output = fallback;
   return output;
}

string BuildEffectiveEaId()
{
   if(StringLen(InpEaId) > 0)
      return SlugPart(InpEaId, "mt5-manual");
   string account = (string)AccountInfoInteger(ACCOUNT_LOGIN);
   string server = AccountInfoString(ACCOUNT_SERVER);
   return "mt5-" + SlugPart(account, "account") + "-" + SlugPart(server, "server") + "-" + IntegerToString((int)InpMagicNumber);
}

string BoolToJson(bool value)
{
   return value ? "true" : "false";
}

bool IsAlphaNum(ushort ch)
{
   return (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9');
}

bool SymbolAliasMatches(string requested, string candidate)
{
   string req = requested;
   string cand = candidate;
   StringTrimLeft(req);
   StringTrimRight(req);
   StringTrimLeft(cand);
   StringTrimRight(cand);
   StringToUpper(req);
   StringToUpper(cand);

   if(req == cand)
      return true;

   int req_len = StringLen(req);
   if(req_len <= 0 || StringLen(cand) <= req_len)
      return false;

   if(StringSubstr(cand, 0, req_len) != req)
      return false;

   ushort next_ch = StringGetCharacter(cand, req_len);
   return !IsAlphaNum(next_ch);
}

bool ResolveTradeSymbol(string requested, string &resolved, string &note)
{
   string req = requested;
   StringTrimLeft(req);
   StringTrimRight(req);
   resolved = req;
   note = "";

   if(req == "")
      return false;

   if(SymbolSelect(req, true))
      return true;

   if(SymbolAliasMatches(req, _Symbol) && SymbolSelect(_Symbol, true))
   {
      resolved = _Symbol;
      note = " mapped_symbol=" + req + "->" + resolved;
      return true;
   }

   for(int selected = 1; selected >= 0; selected--)
   {
      bool selected_only = (selected == 1);
      int total = SymbolsTotal(selected_only);
      for(int i = 0; i < total; i++)
      {
         string candidate = SymbolName(i, selected_only);
         if(SymbolAliasMatches(req, candidate) && SymbolSelect(candidate, true))
         {
            resolved = candidate;
            note = " mapped_symbol=" + req + "->" + resolved;
            return true;
         }
      }
   }

   resolved = req;
   return false;
}

int SkipWhitespace(string text, int pos)
{
   while(pos < StringLen(text))
   {
      ushort ch = (ushort)StringGetCharacter(text, pos);
      if(ch != ' ' && ch != '\t' && ch != '\r' && ch != '\n')
         break;
      pos++;
   }
   return pos;
}

bool ExtractJsonStringAt(string text, int start_quote, string &value, int &next_pos)
{
   if(start_quote < 0 || start_quote >= StringLen(text))
      return false;
   if((ushort)StringGetCharacter(text, start_quote) != '"')
      return false;

   value = "";
   bool escaped = false;
   int len = StringLen(text);
   for(int i = start_quote + 1; i < len; i++)
   {
      ushort ch = (ushort)StringGetCharacter(text, i);
      if(escaped)
      {
         if(ch == 'n')
            value += "\n";
         else if(ch == 'r')
            value += "\r";
         else if(ch == 't')
            value += "\t";
         else
            value += StringSubstr(text, i, 1);
         escaped = false;
         continue;
      }

      if(ch == '\\')
      {
         escaped = true;
         continue;
      }

      if(ch == '"')
      {
         next_pos = i + 1;
         return true;
      }

      value += StringSubstr(text, i, 1);
   }

   return false;
}

bool ExtractJsonObjectAt(string text, int start_brace, string &object_text, int &next_pos)
{
   if(start_brace < 0 || start_brace >= StringLen(text))
      return false;
   if((ushort)StringGetCharacter(text, start_brace) != '{')
      return false;

   bool in_string = false;
   bool escaped = false;
   int depth = 0;
   int len = StringLen(text);

   for(int i = start_brace; i < len; i++)
   {
      ushort ch = (ushort)StringGetCharacter(text, i);
      if(in_string)
      {
         if(escaped)
         {
            escaped = false;
         }
         else if(ch == '\\')
         {
            escaped = true;
         }
         else if(ch == '"')
         {
            in_string = false;
         }
         continue;
      }

      if(ch == '"')
      {
         in_string = true;
         continue;
      }

      if(ch == '{')
         depth++;
      else if(ch == '}')
      {
         depth--;
         if(depth == 0)
         {
            object_text = StringSubstr(text, start_brace, i - start_brace + 1);
            next_pos = i + 1;
            return true;
         }
      }
   }

   return false;
}

bool JsonGetString(string json, string key, string &value)
{
   string marker = "\"" + key + "\":\"";
   int pos = StringFind(json, marker);
   if(pos < 0)
      return false;

   int start_quote = pos + StringLen(marker) - 1;
   int next_pos = 0;
   return ExtractJsonStringAt(json, start_quote, value, next_pos);
}

bool JsonGetObject(string json, string key, string &value)
{
   string marker = "\"" + key + "\":";
   int pos = StringFind(json, marker);
   if(pos < 0)
      return false;

   int brace_pos = SkipWhitespace(json, pos + StringLen(marker));
   int next_pos = 0;
   return ExtractJsonObjectAt(json, brace_pos, value, next_pos);
}

bool JsonGetNumberText(string json, string key, string &value)
{
   string marker = "\"" + key + "\":";
   int pos = StringFind(json, marker);
   if(pos < 0)
      return false;

   int start = SkipWhitespace(json, pos + StringLen(marker));
   int end = start;
   while(end < StringLen(json))
   {
      ushort ch = (ushort)StringGetCharacter(json, end);
      if(ch == ',' || ch == '}' || ch == ']' || ch == ' ' || ch == '\r' || ch == '\n' || ch == '\t')
         break;
      end++;
   }

   value = StringSubstr(json, start, end - start);
   return StringLen(value) > 0;
}

bool JsonGetBool(string json, string key, bool &value)
{
   string text = "";
   if(!JsonGetNumberText(json, key, text))
      return false;

   if(text == "true")
   {
      value = true;
      return true;
   }
   if(text == "false")
   {
      value = false;
      return true;
   }
   return false;
}

string BuildResultRaw(string command_type, string detail)
{
   string raw =
      "{"
      "\"command_type\":\"" + EscapeJson(command_type) + "\","
      + "\"detail\":\"" + EscapeJson(detail) + "\""
      + "}";
   return raw;
}

bool SendApiRequest(string method, string path, string payload, int &status_code, string &response_body)
{
   string url = InpApiBaseUrl + path;
   string headers = "Content-Type: application/json\r\nX-EA-Token: " + InpEaToken + "\r\n";

   uchar body[];
   uchar result[];
   string result_headers = "";

   if(method == "GET")
   {
      ArrayResize(body, 0);
   }
   else
   {
      StringToCharArray(payload, body, 0, WHOLE_ARRAY, CP_UTF8);
      if(ArraySize(body) > 0 && body[ArraySize(body) - 1] == 0)
         ArrayResize(body, ArraySize(body) - 1);
   }

   ResetLastError();
   status_code = WebRequest(method, url, headers, InpRequestTimeoutMs, body, result, result_headers);
   if(status_code == -1)
   {
      int err = GetLastError();
      response_body = "";
      LogMessage("WebRequest failed path=" + path + " error=" + IntegerToString(err));
      return false;
   }

   response_body = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   if(status_code < 200 || status_code >= 300)
   {
      LogMessage("HTTP " + IntegerToString(status_code) + " for " + path + " body=" + response_body);
      return false;
   }

   return true;
}

bool SendHeartbeat()
{
   string strategy_name = MQLInfoString(MQL_PROGRAM_NAME);
   string version = MQLInfoString(MQL_PROGRAM_NAME) + "-0.2.0";
   string broker = AccountInfoString(ACCOUNT_COMPANY);
   string account = (string)AccountInfoInteger(ACCOUNT_LOGIN);

   string payload =
      "{"
      "\"ea_id\":\"" + EscapeJson(g_effective_ea_id) + "\","
      + "\"account_number\":\"" + EscapeJson(account) + "\","
      + "\"broker\":\"" + EscapeJson(broker) + "\","
      + "\"terminal\":\"MT5\","
      + "\"strategy_name\":\"" + EscapeJson(strategy_name) + "\","
      + "\"version\":\"" + EscapeJson(version) + "\","
      + "\"status\":\"online\","
      + "\"allow_trading\":" + BoolToJson(g_allow_trading)
      + "}";

   int status = 0;
   string body = "";
   if(!SendApiRequest("POST", "/api/ea/heartbeat", payload, status, body))
      return false;

   LogMessage("Heartbeat accepted for " + g_effective_ea_id);
   return true;
}

string BuildPositionRawJson(ulong ticket, string symbol, long type)
{
   string raw =
      "{"
      "\"ticket\":\"" + (string)ticket + "\","
      + "\"symbol\":\"" + EscapeJson(symbol) + "\","
      + "\"position_type\":" + IntegerToString((int)type)
      + "}";
   return raw;
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
      double swap = PositionGetDouble(POSITION_SWAP);
      double commission = PositionGetDouble(POSITION_COMMISSION);

      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      if(digits < 0)
         digits = _Digits;

      string item =
         "{"
         "\"ticket\":\"" + (string)ticket + "\","
         + "\"symbol\":\"" + EscapeJson(symbol) + "\","
         + "\"side\":\"" + side + "\","
         + "\"volume\":" + DoubleToString(volume, 2) + ","
         + "\"open_price\":" + DoubleToString(open_price, digits) + ","
         + "\"current_price\":" + DoubleToString(current_price, digits) + ","
         + "\"sl\":" + DoubleToString(sl, digits) + ","
         + "\"tp\":" + DoubleToString(tp, digits) + ","
         + "\"profit\":" + DoubleToString(profit, 2) + ","
         + "\"swap\":" + DoubleToString(swap, 2) + ","
         + "\"commission\":" + DoubleToString(commission, 2) + ","
         + "\"raw\":" + BuildPositionRawJson(ticket, symbol, type)
         + "}";

      if(!first)
         result += ",";
      result += item;
      first = false;
   }

   result += "]";
   return result;
}

bool SendSnapshot()
{
   string account = (string)AccountInfoInteger(ACCOUNT_LOGIN);
   string currency = AccountInfoString(ACCOUNT_CURRENCY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin = AccountInfoDouble(ACCOUNT_MARGIN);
   double free_margin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double margin_level = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   double profit = AccountInfoDouble(ACCOUNT_PROFIT);

   string raw =
      "{"
      "\"company\":\"" + EscapeJson(AccountInfoString(ACCOUNT_COMPANY)) + "\","
      + "\"server\":\"" + EscapeJson(AccountInfoString(ACCOUNT_SERVER)) + "\","
      + "\"leverage\":" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE))
      + "}";

   string payload =
      "{"
      "\"ea_id\":\"" + EscapeJson(g_effective_ea_id) + "\","
      + "\"account_number\":\"" + EscapeJson(account) + "\","
      + "\"currency\":\"" + EscapeJson(currency) + "\","
      + "\"balance\":" + DoubleToString(balance, 2) + ","
      + "\"equity\":" + DoubleToString(equity, 2) + ","
      + "\"margin\":" + DoubleToString(margin, 2) + ","
      + "\"free_margin\":" + DoubleToString(free_margin, 2) + ","
      + "\"margin_level\":" + DoubleToString(margin_level, 2) + ","
      + "\"profit\":" + DoubleToString(profit, 2) + ","
      + "\"positions\":" + BuildPositionsJson() + ","
      + "\"raw\":" + raw
      + "}";

   int status = 0;
   string body = "";
   if(!SendApiRequest("POST", "/api/ea/snapshot", payload, status, body))
      return false;

   LogMessage("Snapshot accepted positions=" + IntegerToString(PositionsTotal()));
   return true;
}

bool ExtractNextCommand(string json, int &offset, int &command_id, string &command_type, string &payload_json)
{
   int id_key = StringFind(json, "\"id\":", offset);
   if(id_key < 0)
      return false;

   int id_start = SkipWhitespace(json, id_key + 5);
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

   string command_slice = StringSubstr(json, id_key);
   if(!JsonGetString(command_slice, "command_type", command_type))
      return false;

   if(!JsonGetObject(command_slice, "payload", payload_json))
      payload_json = "{}";

   offset = id_end;
   return true;
}

bool ClosePositionByTicketText(string ticket_text, string &message)
{
   ulong ticket = (ulong)StringToInteger(ticket_text);
   if(ticket == 0)
   {
      message = "invalid ticket";
      return false;
   }
   if(!PositionSelectByTicket(ticket))
   {
      message = "ticket not found";
      return false;
   }
   if(!g_trade.PositionClose(ticket))
   {
      message = "close failed retcode=" + IntegerToString((int)g_trade.ResultRetcode());
      return false;
   }
   message = "ticket closed";
   return true;
}

bool CancelPendingOrderByTicketText(string ticket_text, string &message)
{
   ulong ticket = (ulong)StringToInteger(ticket_text);
   if(ticket == 0)
   {
      message = "invalid order ticket";
      return false;
   }

   if(!OrderSelect(ticket))
   {
      message = "pending order not found";
      return false;
   }

   if(!g_trade.OrderDelete(ticket))
   {
      message = "cancel order failed retcode=" + IntegerToString((int)g_trade.ResultRetcode());
      return false;
   }

   message = "pending order cancelled";
   return true;
}

bool CloseAllPositions(string &message)
{
   bool ok = true;
   int closed = 0;
   int failed = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(g_trade.PositionClose(ticket))
      {
         closed++;
      }
      else
      {
         failed++;
         ok = false;
      }
   }

   message = "closed=" + IntegerToString(closed) + ", failed=" + IntegerToString(failed);
   return ok;
}

bool ClosePositionsBySymbol(string symbol, string &message)
{
   string resolved_symbol = "";
   string symbol_note = "";
   if(!ResolveTradeSymbol(symbol, resolved_symbol, symbol_note))
   {
      message = (symbol == "" ? "missing symbol" : "failed to select symbol");
      return false;
   }

   bool ok = true;
   int closed = 0;
   int failed = 0;
   bool found = false;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != resolved_symbol)
         continue;

      found = true;
      if(g_trade.PositionClose(ticket))
      {
         closed++;
      }
      else
      {
         failed++;
         ok = false;
      }
   }

   if(!found)
   {
      message = "no open positions for symbol";
      return false;
   }

   message = "symbol=" + resolved_symbol + symbol_note + ", closed=" + IntegerToString(closed) + ", failed=" + IntegerToString(failed);
   return ok;
}

bool OpenPendingOrder(string payload_json, string &message)
{
   string symbol = "";
   string side = "";
   string order_type = "";
   string volume_text = "";
   string price_text = "";
   string comment = "EAControlConnector";
   string sl_text = "";
   string tp_text = "";

   if(!JsonGetString(payload_json, "symbol", symbol))
   {
      message = "missing symbol";
      return false;
   }
   if(!JsonGetString(payload_json, "side", side))
      side = "";
   JsonGetString(payload_json, "order_type", order_type);
   if(!JsonGetNumberText(payload_json, "volume", volume_text))
   {
      message = "missing volume";
      return false;
   }
   if(!JsonGetNumberText(payload_json, "price", price_text) && !JsonGetNumberText(payload_json, "entry_price", price_text))
   {
      message = "missing pending price";
      return false;
   }
   JsonGetString(payload_json, "comment", comment);
   JsonGetNumberText(payload_json, "sl", sl_text);
   JsonGetNumberText(payload_json, "tp", tp_text);

   string resolved_symbol = "";
   string symbol_note = "";
   if(!ResolveTradeSymbol(symbol, resolved_symbol, symbol_note))
   {
      message = "failed to select symbol";
      return false;
   }

   double volume = StringToDouble(volume_text);
   if(volume <= 0)
   {
      message = "invalid volume";
      return false;
   }

   int digits = (int)SymbolInfoInteger(resolved_symbol, SYMBOL_DIGITS);
   double price = NormalizeDouble(StringToDouble(price_text), digits);
   if(price <= 0)
   {
      message = "invalid pending price";
      return false;
   }
   double sl = (sl_text == "" ? 0.0 : NormalizeDouble(StringToDouble(sl_text), digits));
   double tp = (tp_text == "" ? 0.0 : NormalizeDouble(StringToDouble(tp_text), digits));

   g_trade.SetDeviationInPoints(InpTradeDeviationPoints);
   g_trade.SetExpertMagicNumber(InpMagicNumber);

   bool result = false;
   if(order_type == "")
      order_type = side == "sell" ? "sell_limit" : "buy_limit";

   if(order_type == "buy_limit")
      result = g_trade.BuyLimit(volume, price, resolved_symbol, sl, tp, ORDER_TIME_GTC, 0, comment);
   else if(order_type == "sell_limit")
      result = g_trade.SellLimit(volume, price, resolved_symbol, sl, tp, ORDER_TIME_GTC, 0, comment);
   else if(order_type == "buy_stop")
      result = g_trade.BuyStop(volume, price, resolved_symbol, sl, tp, ORDER_TIME_GTC, 0, comment);
   else if(order_type == "sell_stop")
      result = g_trade.SellStop(volume, price, resolved_symbol, sl, tp, ORDER_TIME_GTC, 0, comment);
   else
   {
      message = "unsupported pending order_type";
      return false;
   }

   if(!result)
   {
      message = "pending order failed retcode=" + IntegerToString((int)g_trade.ResultRetcode());
      return false;
   }

   ulong order_ticket = g_trade.ResultOrder();
   message = "pending order placed symbol=" + resolved_symbol + symbol_note + ", type=" + order_type
      + ", volume=" + DoubleToString(volume, 2) + ", order_ticket=" + (string)order_ticket;
   return true;
}

bool OpenMarketOrder(string payload_json, string &message)
{
   string order_mode = "";
   if(JsonGetString(payload_json, "order_mode", order_mode) && order_mode == "pending")
      return OpenPendingOrder(payload_json, message);

   string symbol = "";
   string side = "";
   string volume_text = "";
   string comment = "EAControlConnector";
   string sl_text = "";
   string tp_text = "";

   if(!JsonGetString(payload_json, "symbol", symbol))
   {
      message = "missing symbol";
      return false;
   }
   if(!JsonGetString(payload_json, "side", side))
   {
      message = "missing side";
      return false;
   }
   if(!JsonGetNumberText(payload_json, "volume", volume_text))
   {
      message = "missing volume";
      return false;
   }
   JsonGetString(payload_json, "comment", comment);
   JsonGetNumberText(payload_json, "sl", sl_text);
   JsonGetNumberText(payload_json, "tp", tp_text);

   string resolved_symbol = "";
   string symbol_note = "";
   if(!ResolveTradeSymbol(symbol, resolved_symbol, symbol_note))
   {
      message = "failed to select symbol";
      return false;
   }

   double volume = StringToDouble(volume_text);
   if(volume <= 0)
   {
      message = "invalid volume";
      return false;
   }

   int digits = (int)SymbolInfoInteger(resolved_symbol, SYMBOL_DIGITS);
   double sl = (sl_text == "" ? 0.0 : NormalizeDouble(StringToDouble(sl_text), digits));
   double tp = (tp_text == "" ? 0.0 : NormalizeDouble(StringToDouble(tp_text), digits));

   g_trade.SetDeviationInPoints(InpTradeDeviationPoints);
   g_trade.SetExpertMagicNumber(InpMagicNumber);

   bool result = false;
   if(side == "buy")
      result = g_trade.Buy(volume, resolved_symbol, 0.0, sl, tp, comment);
   else if(side == "sell")
      result = g_trade.Sell(volume, resolved_symbol, 0.0, sl, tp, comment);
   else
   {
      message = "unsupported side";
      return false;
   }

   if(!result)
   {
      message = "open failed retcode=" + IntegerToString((int)g_trade.ResultRetcode());
      return false;
   }

   message = "order placed symbol=" + resolved_symbol + symbol_note + ", side=" + side + ", volume=" + DoubleToString(volume, 2);
   return true;
}

bool UpdateRuntimeParams(string payload_json, string &message)
{
   bool changed = false;
   bool bool_value = false;
   string number_text = "";
   string summary = "";

   if(JsonGetBool(payload_json, "allow_trading", bool_value))
   {
      g_allow_trading = bool_value;
      summary += "allow_trading=" + BoolToJson(bool_value) + "; ";
      changed = true;
   }

   if(JsonGetNumberText(payload_json, "heartbeat_interval_sec", number_text))
   {
      int value = (int)StringToInteger(number_text);
      if(value > 0)
      {
         g_heartbeat_interval_sec = value;
         summary += "heartbeat_interval_sec=" + IntegerToString(value) + "; ";
         changed = true;
      }
   }

   if(JsonGetNumberText(payload_json, "snapshot_interval_sec", number_text))
   {
      int value = (int)StringToInteger(number_text);
      if(value > 0)
      {
         g_snapshot_interval_sec = value;
         summary += "snapshot_interval_sec=" + IntegerToString(value) + "; ";
         changed = true;
      }
   }

   if(JsonGetNumberText(payload_json, "command_poll_interval_sec", number_text))
   {
      int value = (int)StringToInteger(number_text);
      if(value > 0)
      {
         g_command_poll_interval_sec = value;
         summary += "command_poll_interval_sec=" + IntegerToString(value) + "; ";
         changed = true;
      }
   }

   if(!changed)
   {
      message = "no supported params in payload";
      return false;
   }

   message = summary;
   return true;
}

bool SubmitCommandResult(int command_id, string status_text, string message, string raw_json)
{
   string payload =
      "{"
      "\"status\":\"" + status_text + "\","
      + "\"message\":\"" + EscapeJson(message) + "\"";

   if(raw_json != "")
      payload += ",\"raw\":" + raw_json;

   payload += "}";

   int status = 0;
   string body = "";
   string path = "/api/ea/commands/" + (string)command_id + "/result";
   if(!SendApiRequest("POST", path, payload, status, body))
      return false;

   return true;
}

void ExecuteCommand(int command_id, string command_type, string payload_json)
{
   string executing_message = "command started";
   SubmitCommandResult(command_id, "executing", executing_message, BuildResultRaw(command_type, executing_message));

   bool success = false;
   string message = "unsupported command_type";

   if(command_type == "pause_trading")
   {
      g_allow_trading = false;
      success = true;
      message = "trading paused";
   }
   else if(command_type == "resume_trading")
   {
      g_allow_trading = true;
      success = true;
      message = "trading resumed";
   }
   else if(command_type == "close_all")
   {
      success = CloseAllPositions(message);
   }
   else if(command_type == "close_symbol")
   {
      string symbol = "";
      if(JsonGetString(payload_json, "symbol", symbol))
         success = ClosePositionsBySymbol(symbol, message);
      else
         message = "missing symbol";
   }
   else if(command_type == "close_ticket")
   {
      string ticket = "";
      if(JsonGetString(payload_json, "ticket", ticket) || JsonGetNumberText(payload_json, "ticket", ticket))
         success = ClosePositionByTicketText(ticket, message);
      else
         message = "missing ticket";
   }
   else if(command_type == "cancel_order")
   {
      string ticket = "";
      if(JsonGetString(payload_json, "ticket", ticket) || JsonGetNumberText(payload_json, "ticket", ticket)
         || JsonGetString(payload_json, "order_ticket", ticket) || JsonGetNumberText(payload_json, "order_ticket", ticket))
         success = CancelPendingOrderByTicketText(ticket, message);
      else
         message = "missing order ticket";
   }
   else if(command_type == "manual_manage")
   {
      success = true;
      message = "manual management marker acknowledged";
   }
   else if(command_type == "manual_release")
   {
      success = true;
      message = "manual management release marker acknowledged";
   }
   else if(command_type == "open_order")
   {
      success = OpenMarketOrder(payload_json, message);
   }
   else if(command_type == "update_params")
   {
      success = UpdateRuntimeParams(payload_json, message);
   }
   else
   {
      message = "unsupported command_type: " + command_type;
   }

   string final_status = success ? "success" : "failed";
   string raw = BuildResultRaw(command_type, message);
   if(!SubmitCommandResult(command_id, final_status, message, raw))
      LogMessage("Failed to submit result for command_id=" + IntegerToString(command_id));

   LogMessage("Command " + IntegerToString(command_id) + " " + command_type + " -> " + final_status + " (" + message + ")");
}

bool PollAndExecuteCommands()
{
   int status = 0;
   string body = "";
   string path = "/api/ea/commands?ea_id=" + g_effective_ea_id;

   if(!SendApiRequest("GET", path, "", status, body))
      return false;

   int offset = 0;
   int cmd_id = 0;
   string cmd_type = "";
   string payload_json = "{}";
   int executed = 0;

   while(ExtractNextCommand(body, offset, cmd_id, cmd_type, payload_json))
   {
      ExecuteCommand(cmd_id, cmd_type, payload_json);
      executed++;
   }

   if(executed > 0)
      LogMessage("Processed commands=" + IntegerToString(executed));
   return true;
}

int OnInit()
{
   g_allow_trading = InpAllowTradingOnStart;
   g_heartbeat_interval_sec = MathMax(1, InpHeartbeatIntervalSec);
   g_snapshot_interval_sec = MathMax(1, InpSnapshotIntervalSec);
   g_command_poll_interval_sec = MathMax(1, InpCommandPollIntervalSec);
   g_effective_ea_id = BuildEffectiveEaId();

   g_trade.SetDeviationInPoints(InpTradeDeviationPoints);
   g_trade.SetExpertMagicNumber(InpMagicNumber);

   EventSetTimer(1);
   LogMessage("Initialized ea_id=" + g_effective_ea_id);
   LogMessage("Allow WebRequest for " + InpApiBaseUrl + " in MT5 terminal settings");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   LogMessage("Stopped reason=" + IntegerToString(reason));
}

void OnTick()
{
   // Strategy trading logic can check g_allow_trading before opening new trades.
   if(!g_allow_trading)
      return;
}

void OnTimer()
{
   datetime now = TimeLocal();

   if(now - g_last_heartbeat >= g_heartbeat_interval_sec)
   {
      if(SendHeartbeat())
         g_last_heartbeat = now;
   }

   if(now - g_last_snapshot >= g_snapshot_interval_sec)
   {
      if(SendSnapshot())
         g_last_snapshot = now;
   }

   if(now - g_last_command_poll >= g_command_poll_interval_sec)
   {
      if(PollAndExecuteCommands())
         g_last_command_poll = now;
   }
}
