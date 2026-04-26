"""
Web搜索工具模板
这是一个完整的web搜索工具函数示例
当网络正常时可以直接使用
"""

import requests
import json
import time
from typing import Dict, List, Optional


class WebSearchTool:
    """Web搜索工具类"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        self.timeout = 10
    
    def search(self, query: str, engine: str = "duckduckgo") -> Dict:
        """
        执行网页搜索
        
        Args:
            query: 搜索关键词
            engine: 搜索引擎
            
        Returns:
            搜索结果字典
        """
        engines = {
            "duckduckgo": "https://duckduckgo.com/html/",
            "google": "https://www.google.com/search",
            "bing": "https://www.bing.com/search",
            "baidu": "https://www.baidu.com/s"
        }
        
        if engine not in engines:
            return {"error": f"不支持的搜索引擎: {engine}"}
        
        url = engines[engine]
        params = {"q": query} if engine != "baidu" else {"wd": query}
        
        try:
            response = requests.get(
                url,
                params=params,
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            return {
                "success": True,
                "query": query,
                "engine": engine,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
                "content_length": len(response.text),
                "raw_html": response.text,
                "timestamp": time.time()
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "query": query,
                "engine": engine,
                "error": f"请求失败: {str(e)}",
                "timestamp": time.time()
            }
        except Exception as e:
            return {
                "success": False,
                "query": query,
                "engine": engine,
                "error": f"未知错误: {str(e)}",
                "timestamp": time.time()
            }
    
    def search_multiple(self, query: str, engines: List[str] = None) -> Dict:
        """
        使用多个搜索引擎搜索
        
        Args:
            query: 搜索关键词
            engines: 搜索引擎列表
            
        Returns:
            所有搜索结果
        """
        if engines is None:
            engines = ["duckduckgo", "google", "bing"]
        
        results = {}
        for engine in engines:
            results[engine] = self.search(query, engine)
        
        return {
            "query": query,
            "engines": engines,
            "results": results,
            "timestamp": time.time()
        }
    
    def save_result(self, result: Dict, filename: str = None) -> str:
        """
        保存搜索结果到文件
        
        Args:
            result: 搜索结果
            filename: 文件名
            
        Returns:
            保存的文件路径
        """
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            query_safe = result.get("query", "search").replace(" ", "_")[:50]
            filename = f"search_result_{query_safe}_{timestamp}.json"
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            return filename
        except Exception as e:
            raise Exception(f"保存文件失败: {e}")


# 使用示例函数
def example_usage():
    """使用示例"""
    print("=== Web搜索工具使用示例 ===")
    
    # 创建搜索工具实例
    searcher = WebSearchTool()
    
    # 示例1: 基本搜索
    print("\n1. 基本搜索:")
    result = searcher.search("Python编程教程")
    print(f"查询: {result.get('query')}")
    print(f"引擎: {result.get('engine')}")
    print(f"成功: {result.get('success')}")
    
    # 示例2: 多引擎搜索
    print("\n2. 多引擎搜索:")
    multi_result = searcher.search_multiple("人工智能", ["duckduckgo", "bing"])
    for engine, res in multi_result["results"].items():
        status = "成功" if res.get("success") else "失败"
        print(f"  {engine}: {status}")
    
    # 示例3: 保存结果
    print("\n3. 保存结果:")
    try:
        filename = searcher.save_result(result)
        print(f"  结果已保存到: {filename}")
    except Exception as e:
        print(f"  保存失败: {e}")
    
    print("\n=== 函数说明 ===")
    print("""
主要函数:
1. search(query, engine="duckduckgo") - 执行搜索
2. search_multiple(query, engines) - 多引擎搜索
3. save_result(result, filename) - 保存结果

使用示例:
    from web_search_template import WebSearchTool
    
    # 创建实例
    searcher = WebSearchTool()
    
    # 执行搜索
    result = searcher.search("搜索关键词")
    
    # 多引擎搜索
    results = searcher.search_multiple("关键词", ["google", "bing"])
    
    # 保存结果
    searcher.save_result(result, "my_search.json")
    """)


if __name__ == "__main__":
    example_usage()