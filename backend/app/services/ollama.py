import ollama
import json
import re
from app.core.config import settings

class OllamaService:
    def __init__(self):
        self.client = ollama.AsyncClient(host=settings.OLLAMA_HOST)

    async def analyze_image(self, image_path: str) -> dict:
        """
        Analyzes a food product image to identify product name, category,
        expiration date, and a confidence score.

        Args:
            image_path: The path to the image file within the container.

        Returns:
            A dictionary containing the analysis results.
        """
        prompt = (
            "Analyze the attached image of a food product. "
            "Identify the following information: "
            "1. `product_name`: The full name of the product. "
            "2. `category`: A likely category (e.g., 'dairy', 'produce', 'meat', 'pantry', 'beverage', 'frozen'). "
            "3. `expiry_date`: The expiration date in YYYY-MM-DD format. If not visible, estimate it or return null. "
            "4. `confidence_score`: A float between 0.0 and 1.0 indicating your confidence in the accuracy of the extracted information. "
            "Provide the response ONLY as a valid JSON object with these keys."
        )
        
        try:
            response = await self.client.chat(
                model='qwen2-vl:7b',
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [image_path]
                }],
                options={"temperature": 0.2} # Lower temperature for more predictable JSON output
            )
            
            content = response['message']['content']
            # Use regex to find the JSON object, which is more robust
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                json_content = match.group(0)
                parsed_response = json.loads(json_content)
            else:
                # Fallback if no JSON is found
                parsed_response = {}

            return {
                "product_name": parsed_response.get("product_name", "Unknown"),
                "category": parsed_response.get("category", "Unknown"),
                "expiry_date": parsed_response.get("expiry_date"),
                "confidence_score": parsed_response.get("confidence_score", 0.0)
            }

        except Exception as e:
            print(f"Error analyzing image with Ollama: {e}")
            return {
                "product_name": "Error Processing",
                "category": "Unknown",
                "expiry_date": None,
                "confidence_score": 0.0
            }

ollama_service = OllamaService()