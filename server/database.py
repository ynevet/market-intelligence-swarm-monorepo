import datetime
import logging
import os

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

logger = logging.getLogger("market_intel.database")

class MongoHandler:
    def __init__(self):
        self.uri = os.environ.get("MONGO_URI")
        self.client = None
        self.db = None
        self.logs = None
        self.reports = None
        
        if self.uri:
            try:
                self.client = MongoClient(self.uri)
                self.db = self.client.get_database("market_swarm_db")
                self.logs = self.db.get_collection("agent_logs")
                self.reports = self.db.get_collection("final_reports")
                logger.info("Connected to MongoDB Atlas")
            except ConnectionFailure as e:
                logger.exception("MongoDB connection failed: %s", e)
        else:
            logger.warning("MONGO_URI not found. Database logging is disabled.")

    def log_query(self, session_id: str, query: str, user_info: dict = None):
        if self.logs is not None:
            doc = {
                "session_id": session_id,
                "timestamp": datetime.datetime.utcnow(),
                "agent": "User",
                "action": "Initial Query",
                "content": query
            }
            if user_info:
                doc.update({k: v for k, v in user_info.items() if v is not None})
            self.logs.insert_one(doc)

    def log_step(self, session_id: str, agent_name: str, action: str, content: str):
        if self.logs is not None:
            doc = {
                "session_id": session_id,
                "timestamp": datetime.datetime.utcnow(),
                "agent": agent_name,
                "action": action,
                "content": str(content)[:2000]  # truncate long content
            }
            self.logs.insert_one(doc)

    def log_final_report(self, session_id: str, final_report: dict, metadata: dict = None):
        if self.reports is not None:
            doc = {
                "session_id": session_id,
                "timestamp": datetime.datetime.utcnow(),
                "report": final_report
            }
            if metadata:
                doc.update(metadata)
            self.reports.insert_one(doc)

db_handler = MongoHandler()