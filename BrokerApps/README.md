# Broker Apps

Small Spring Boot apps, one per broker, that:
- fetch **funds, holdings, positions and orders** into PostgreSQL on a schedule;
- **place, modify and cancel orders**;
- serve live **profile, funds, holdings, positions, orders, trades and quotes** over a REST API.

```
BrokerApps/
  broker-common/   shared library - DB tables, sync, order safety checks, REST API
  zerodha-app/     Zerodha (Kite Connect) app, port 8091
```

Every broker app has the same API. Only the broker-specific part differs: one class implementing
[`Broker`](broker-common/src/main/java/com/trademarkets/broker/common/broker/Broker.java), plus its login.
All apps share one database. Every row is tagged with its broker and account.

## First-time setup

1. **Database** - create it once (or in pgAdmin: Databases → Create → `trademarkets`):
   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres trademarkets
   ```
   Tables are created by Flyway on first start (`broker-common/src/main/resources/db/migration`).
2. **Kite Connect app** - at https://developers.kite.trade create one app per Zerodha account with
   Redirect URL `http://localhost:8091/api/kite/callback`.
3. **Secrets** - `zerodha-app/src/main/resources/secrets.properties` (git-ignored; template in
   `secrets.properties.example`). Fill in the Postgres password and each account's API key and secret:
   ```properties
   broker.accounts.main.api-key=...
   broker.accounts.main.api-secret=...
   broker.accounts.family.api-key=...
   broker.accounts.family.api-secret=...
   ```
   `broker.encryption-key` is already generated. Don't change it, or saved logins can't be read.
4. **Start** - VS Code task *Brokers: start zerodha-app*, or:
   ```powershell
   .\mvnw install -DskipTests
   .\mvnw -pl zerodha-app spring-boot:run
   ```
5. **Log in (every day)** - Kite logins expire at 06:00 IST. Open
   http://localhost:8091/api/accounts/main/login in a browser and log in at Zerodha. The app saves the
   token (encrypted) and runs a first sync. Until then, syncs skip that account.

## Settings (`zerodha-app/src/main/resources`)

| File | Contents |
|---|---|
| `application.properties` | port 8091, only reachable from this computer; imports the files below |
| `database.properties` | PostgreSQL URL and user |
| `zerodha.properties` | Kite API and login URLs, daily token expiry time |
| `sync.properties` | schedule (every 15 min, 09:00-15:45 Mon-Fri, and at startup), snapshot retention (90 days) |
| `trading.properties` | **`trading.enabled=false`** (orders blocked) and `trading.max-order-value=50000` |
| `logging.properties` | log folder, 7-day retention |
| `secrets.properties` | DB password, encryption key, account API keys (git-ignored) |

Logs go to `TradeMarkets/logFiles/zerodhaApp/{application,sync,orders,api,errors}`. Every order request
is written to `orders/`.

## Order safety

- Placing and modifying orders is **off** until you set `trading.enabled=true`. Cancelling always works.
- Orders above `trading.max-order-value` are rejected. Market orders are valued at the last price,
  which needs market-data access (see below).
- Order calls are never retried, so an order is never sent twice.
- The API listens on `127.0.0.1` only, so other devices on your network can't reach it.
- Zerodha requires order API calls to come from a static IP registered in your Kite developer console
  (SEBI rule for API trading). Reading data works without it. Check developers.kite.trade for current rules.

## API (same for every broker app)

| Method | Path | |
|---|---|---|
| GET | `/api/info` | broker, accounts, trading switches |
| GET | `/api/accounts` | accounts with login and last-sync state |
| GET | `/api/accounts/{a}/login` | log in at the broker (open in browser) |
| POST | `/api/accounts/{a}/logout` | forget the saved token |
| GET | `/api/accounts/{a}/profile` | broker profile |
| GET | `/api/accounts/{a}/funds` | cash / margin per segment |
| GET | `/api/accounts/{a}/holdings` | holdings |
| GET | `/api/accounts/{a}/positions` | open positions |
| GET | `/api/accounts/{a}/orders` | today's orders |
| GET | `/api/accounts/{a}/trades` | today's fills |
| GET | `/api/accounts/{a}/quotes?instruments=NSE:INFY,NSE:TCS` | quotes (needs Kite market-data plan) |
| POST | `/api/accounts/{a}/orders` | place an order |
| PUT | `/api/accounts/{a}/orders/{id}` | modify (any of `type`, `quantity`, `price`, `triggerPrice`) |
| DELETE | `/api/accounts/{a}/orders/{id}` | cancel |
| POST | `/api/sync`, `/api/accounts/{a}/sync` | sync now |

Errors come back as JSON with a `detail` message: 401 = log in again, 403 = trading disabled,
400 = bad or blocked order, 502 = the broker refused.

Place an order (PowerShell):
```powershell
Invoke-RestMethod -Method Post http://localhost:8091/api/accounts/main/orders -ContentType application/json -Body '{
  "symbol": "INFY", "exchange": "NSE", "side": "BUY", "type": "LIMIT", "product": "CNC",
  "quantity": 1, "price": 1400 }'
```
`type` is `MARKET`, `LIMIT`, `SL` (needs `price` and `triggerPrice`) or `SL_M` (needs `triggerPrice`).
`product` is `CNC` (delivery), `MIS` (intraday) or `NRML` (F&O). Optional fields: `validity` (default `DAY`),
`afterMarket: true` for an AMO, and `tag`.

## Database tables

| Table | What |
|---|---|
| `broker_account` | one row per configured account: login state (token encrypted), last sync result |
| `funds_snapshot`, `holding_snapshot`, `position_snapshot` | one set of rows per sync, stamped `taken_at` |
| `broker_order` | every order, updated on each sync; `placed_by_app` marks orders placed through this API |

Latest holdings of an account, for example:
```sql
select h.* from holding_snapshot h join broker_account a on a.id = h.account_id
where a.name = 'main' and h.taken_at = (select max(taken_at) from holding_snapshot where account_id = a.id);
```

## Adding another broker

1. Copy `zerodha-app` to `xyz-app` and add `<module>xyz-app</module>` to the root `pom.xml`.
2. Replace the `zerodha` package with a class that implements `Broker` (`name()` returns e.g. `"XYZ"`).
   Throw `BrokerException(message, true)` when the broker says the login is invalid.
3. Add a login controller if the broker needs one. Brokers with long-lived tokens can skip it:
   put `broker.accounts.<name>.access-token=` in `secrets.properties` instead.
4. Change the port in `application.properties` and the log folder in `logging.properties`.

The DB tables, sync, safety checks and REST API come from broker-common unchanged.

## Tests

`.\mvnw test` (or VS Code task *Brokers: run tests*) uses an in-memory H2 database and a fake broker
or fake Kite server, so it never touches PostgreSQL or real accounts.
