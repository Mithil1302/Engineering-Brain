#!/usr/bin/env python3
"""
Test script to list available Gemini embedding models.
"""
import os
from google import genai

# Get API key from environment
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERROR: GEMINI_API_KEY environment variable not set")
    sys.exit(1)

print("Testing Gemini API...")
print(f"API Key: {api_key[:20]}...")
print("-" * 80)

try:
    client = genai.Client(api_key=api_key)
    
    # List all available models
    print("\nListing all available models:")
    models = client.models.list()
    
    print("\nAll models:")
    for model in models:
        print(f"  - {model.name}")
        if hasattr(model, 'supported_generation_methods'):
            print(f"    Methods: {model.supported_generation_methods}")
    
    print("\n" + "=" * 80)
    print("Embedding-capable models:")
    for model in models:
        if hasattr(model, 'supported_generation_methods'):
            if 'embedContent' in model.supported_generation_methods or 'embed' in str(model.supported_generation_methods).lower():
                print(f"  ✓ {model.name}")
                print(f"    Methods: {model.supported_generation_methods}")
        
except Exception as e:
    print(f"\n✗ Error: {e}")
    print(f"Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()
