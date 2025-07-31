import ollama
import json
from app.core.config import settings

class OllamaService:
    def __init__(self):
        self.client = ollama.AsyncClient(host=settings.OLLAMA_HOST)

    async def analyze_image(self, image_path: str) -> dict:
        """
        Analyzes a food product image to identify the product name and category.

        Args:
            image_path: The path to the image file within the container.

        Returns:
            A dictionary containing the 'product_name' and 'category'.
        """
        prompt = (
            "Analyze the attached image of a food product. "
            "Identify the product name and a likely category "
            "(e.g., 'dairy', 'produce', 'meat', 'pantry', 'beverage', 'frozen'). "
            "Provide the response as a JSON object with the keys 'product_name' and 'category'."
        )
        
        try:
            response = await self.client.chat(
                model='qwen2.5vl:7b',
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [image_path]
                }]
            )
            
            content = response['message']['content']
            # Clean the response to extract only the JSON part
            json_content = content[content.find('{'):content.rfind('}')+1]
            
            parsed_response = json.loads(json_content)
            return parsed_response

        except Exception as e:
            # In a real app, you'd have more robust logging and error handling
            print(f"Error analyzing image with Ollama: {e}")
            return {
                "product_name": "Unknown",
                "category": "Unknown"
            }

ollama_service = OllamaService()
