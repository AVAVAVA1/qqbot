import asyncio
import json
from typing import Union, List, Dict, Any, Optional


class MessageSegment:
    
    @staticmethod
    def text(content: str) -> Dict[str, Any]:
        return {"type": "text", "data": {"text": content}}
    
    @staticmethod
    def image(url: str = None, file: str = None) -> Dict[str, Any]:
        data = {}
        if url:
            data["url"] = url
        if file:
            data["file"] = file
        return {"type": "image", "data": data}
    
    @staticmethod
    def at(user_id: Union[int, str]) -> Dict[str, Any]:
        return {"type": "at", "data": {"qq": str(user_id)}}
    
    @staticmethod
    def reply(message_id: int) -> Dict[str, Any]:
        return {"type": "reply", "data": {"id": message_id}}
    
    @staticmethod
    def face(id: int) -> Dict[str, Any]:
        return {"type": "face", "data": {"id": id}}
    
    @staticmethod
    def record(url: str = None, file: str = None) -> Dict[str, Any]:
        data = {}
        if url:
            data["url"] = url
        if file:
            data["file"] = file
        return {"type": "record", "data": data}
    
    @staticmethod
    def video(url: str = None, file: str = None) -> Dict[str, Any]:
        data = {}
        if url:
            data["url"] = url
        if file:
            data["file"] = file
        return {"type": "video", "data": data}


class ApiClient:
    
    def __init__(self):
        self.ws = None
        self._echo_counter = 0
        self._pending_requests: Dict[str, asyncio.Future] = {}
    
    def set_ws(self, ws):
        self.ws = ws
    
    async def _call_api(self, action: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.ws:
            raise RuntimeError("WebSocket 未连接")
        
        self._echo_counter += 1
        echo = str(self._echo_counter)
        
        request = {
            "action": action,
            "params": params or {},
            "echo": echo
        }
        
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[echo] = future
        
        await self.ws.send(json.dumps(request))
        
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            del self._pending_requests[echo]
            raise TimeoutError(f"API 调用超时: {action}")
    
    async def send_private_msg(
        self,
        user_id: Union[int, str],
        message: Union[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        if isinstance(message, str):
            message = [MessageSegment.text(message)]
        
        params = {
            "user_id": int(user_id),
            "message": message
        }
        return await self._call_api("send_private_msg", params)
    
    async def send_group_msg(
        self,
        group_id: Union[int, str],
        message: Union[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        if isinstance(message, str):
            message = [MessageSegment.text(message)]
        
        params = {
            "group_id": int(group_id),
            "message": message
        }
        return await self._call_api("send_group_msg", params)
    
    async def send_msg(
        self,
        message_type: str,
        user_id: Union[int, str] = None,
        group_id: Union[int, str] = None,
        message: Union[str, List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        if isinstance(message, str):
            message = [MessageSegment.text(message)]
        
        params = {
            "message_type": message_type,
            "message": message
        }
        
        if message_type == "private" and user_id:
            params["user_id"] = int(user_id)
        elif message_type == "group" and group_id:
            params["group_id"] = int(group_id)
        
        return await self._call_api("send_msg", params)
    
    async def delete_msg(self, message_id: int) -> Dict[str, Any]:
        return await self._call_api("delete_msg", {"message_id": message_id})
    
    async def get_msg(self, message_id: int) -> Dict[str, Any]:
        return await self._call_api("get_msg", {"message_id": message_id})
    
    async def get_login_info(self) -> Dict[str, Any]:
        return await self._call_api("get_login_info")
    
    async def get_friend_list(self) -> Dict[str, Any]:
        return await self._call_api("get_friend_list")
    
    async def get_group_list(self) -> Dict[str, Any]:
        return await self._call_api("get_group_list")
    
    async def get_group_member_list(self, group_id: Union[int, str]) -> Dict[str, Any]:
        return await self._call_api("get_group_member_list", {"group_id": int(group_id)})


api = ApiClient()
