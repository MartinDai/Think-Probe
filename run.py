import os

import uvicorn

from app.main import app
from app.utils.logger import logger

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8080))
    logger.info("Think Probe Starting...")
    uvicorn.run(app, host=host, port=port, workers=1, access_log=False, reload=False)
