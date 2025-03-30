import uvicorn

from app.main import app
from app.utils.logger import logger

if __name__ == "__main__":
    logger.info("Starting Think Probe...")
    uvicorn.run(app, host="0.0.0.0", port=8080, workers=1, access_log=False, reload=False)
