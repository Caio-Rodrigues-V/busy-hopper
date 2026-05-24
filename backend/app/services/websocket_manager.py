import logging
from fastapi import WebSocket
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Mapping company_id -> list of active WebSocket connections
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, company_id: int):
        await websocket.accept()
        if company_id not in self.active_connections:
            self.active_connections[company_id] = []
        self.active_connections[company_id].append(websocket)
        logger.info(f"Client connected to company {company_id}. Active connections: {len(self.active_connections[company_id])}")

    def disconnect(self, websocket: WebSocket, company_id: int):
        if company_id in self.active_connections:
            if websocket in self.active_connections[company_id]:
                self.active_connections[company_id].remove(websocket)
            if not self.active_connections[company_id]:
                del self.active_connections[company_id]
        logger.info(f"Client disconnected from company {company_id}")

    async def broadcast_to_company(self, company_id: int, message: Any):
        if company_id in self.active_connections:
            # We copy the list to avoid mutations during iteration
            for connection in list(self.active_connections[company_id]):
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.debug(f"Failed to send websocket message: {e}")
                    # Remove stale connections
                    try:
                        self.active_connections[company_id].remove(connection)
                    except ValueError:
                        pass

manager = ConnectionManager()
