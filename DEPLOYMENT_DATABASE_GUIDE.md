# Database Configuration for Deployment

## ✅ Current Status

Your Replit PostgreSQL database is already provisioned and configured for development. This guide explains how to ensure it works correctly during deployment.

## Database Connection Details

### Development Environment
- **Connection String:** Available in `DATABASE_URL` environment variable
- **Database Type:** PostgreSQL (Neon-hosted)
- **Status:** ✅ Working

### Deployment Environment Configuration

The deployment needs access to the same database. Here's how it's configured:

#### 1. Environment Variables Required

The following environment variables are **automatically available** in Replit deployments:

- `DATABASE_URL` - PostgreSQL connection string (automatically injected)
- `SECRET_KEY` - Application secret key (already configured in Secrets)

#### 2. Database Connection in app.py

The app is configured to:
1. **Primary:** Use `DATABASE_URL` environment variable
2. **Fallback:** Use `DATABASE_URI` if DATABASE_URL is not available  
3. **Last Resort:** SQLite for local development

```python
database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI")

if not database_url:
    database_url = "sqlite:///instance/league.db"
    logging.warning("No DATABASE_URL found, using SQLite fallback")
```

#### 3. Connection Pool Settings

Optimized for production:
```python
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,      # Verify connections before using
    "pool_recycle": 300,         # Recycle connections after 5 minutes
    "connect_args": {
        "connect_timeout": 10,   # 10 second connection timeout
    }
}
```

## Database Initialization

### Automatic Lazy Initialization

The database tables are created automatically on first use (not during health checks):

1. **Health checks** - Skip database entirely (fast response)
2. **First real request** - Initialize database tables if needed
3. **Subsequent requests** - Use existing tables

### Error Handling

If database connection fails:
- Application will still start (health checks pass)
- Error logged for debugging
- Database features won't work until connection is restored

## Troubleshooting Deployment Issues

### Error: "could not translate host name"

**Cause:** Database URL not available in deployment environment

**Solution:**
1. Verify DATABASE_URL is in Replit Secrets
2. Check deployment logs for actual connection string being used
3. Ensure deployment has access to the same database as development

### Error: "Application is failing health checks"

**Cause:** Database initialization blocking startup

**Solution:** ✅ Already fixed
- Health check endpoint (`/health`) doesn't use database
- Database initialization happens lazily after health checks pass

### Error: "Database connection timeout"

**Cause:** Network issues or database not responding

**Solution:**
- Check database status in Replit UI
- Verify connection string is correct
- Increase `connect_timeout` if needed (currently 10s)

## Health Check Configuration

### Use `/health` Endpoint

Configure your deployment health checks to use:

**Endpoint:** `/health`  
**Expected Response:** `{"status": "ok"}`  
**HTTP Status:** 200  
**Response Time:** ~2-3ms

### Why Not Use `/` for Health Checks?

The root endpoint (`/`) performs database queries to count teams and matches, which:
- Takes longer (50-100ms vs 2-3ms)
- Can fail if database is temporarily unavailable
- Not ideal for health check monitoring

## Verification Steps

After deployment, verify database connection:

1. **Check Health Endpoint**
   ```bash
   curl https://your-deployment-url.replit.app/health
   # Expected: {"status":"ok"}
   ```

2. **Check Application Logs**
   Look for:
   - ✅ "Database already initialized with X tables"
   - ❌ "Database initialization failed" (indicates problem)

3. **Test Database Features**
   - Navigate to your app
   - Try registering a team
   - Verify data persists

## Database Tables

Your database includes these tables:
- `team` - Team information
- `free_agent` - Free agent registrations  
- `match` - Match records and results
- `reschedule` - Reschedule requests
- `substitute` - Substitute player records
- `player` - Individual player statistics

## Production Best Practices

1. ✅ **Connection pooling enabled** - Efficient connection reuse
2. ✅ **Pool pre-ping enabled** - Detects stale connections
3. ✅ **Connection recycling** - Prevents connection timeouts
4. ✅ **Lazy initialization** - Fast startup, no blocking
5. ✅ **Error handling** - Graceful degradation if DB unavailable

## Need Help?

If you encounter database issues during deployment:

1. Check the deployment logs for specific error messages
2. Verify DATABASE_URL is accessible in deployment environment
3. Ensure your Replit PostgreSQL database is active
4. Contact Replit support if database service is unavailable

---

**Status:** Database configuration optimized for deployment ✅
