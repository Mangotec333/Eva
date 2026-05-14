from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
import logging

logger = logging.getLogger(__name__)

def create_scheduler(app):
    scheduler = AsyncIOScheduler()

    async def nightly_generate():
        logger.info("Nightly draft generation starting...")
        try:
            resp = requests.post("http://localhost:8767/drafts/generate-from-eva", timeout=30)
            logger.info(f"Nightly generation: {resp.status_code}")
        except Exception as e:
            logger.error(f"Nightly generation failed: {e}")

    async def fetch_performance():
        logger.info("Fetching post performance metrics...")

    scheduler.add_job(nightly_generate, "cron", hour=23, minute=0, id="nightly_generate")
    scheduler.add_job(fetch_performance, "interval", hours=6, id="fetch_performance")
    return scheduler
