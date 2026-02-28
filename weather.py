import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import requests

# Add these two lines to import dotenv
from dotenv import load_dotenv
load_dotenv()  # This loads the variables from the .env file

# Automatically add the 'lib' directory relative to the script's location
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(script_dir, 'lib'))

# Import the specific driver for the 7.5inch (B) V2 display
from waveshare_epd import epd7in5b_V2

# --- USER CONFIGURATION ---
# Replace your hardcoded API_KEY with os.getenv
API_KEY = os.getenv('OPENWEATHER_API_KEY') 

if not API_KEY:
    raise ValueError("No API key found! Please check your .env file.")

LOCATION = 'Hervantajärvi'
LATITUDE = '61.4285'
LONGITUDE = '23.8783'
UNITS = 'metric'

BASE_URL = 'https://api.openweathermap.org/data/3.0/onecall'
FONT_DIR = os.path.join(script_dir, 'font')
PIC_DIR = os.path.join(script_dir, 'pic')
ICON_DIR = os.path.join(PIC_DIR, 'icon')

# --- LOGGING CONFIGURATION ---
LOG_FILE = os.path.join(script_dir, 'weather_display.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3),
        logging.StreamHandler(sys.stdout)
    ]
)

# --- FONT & COLOR CONFIGURATION ---
font22 = ImageFont.truetype(os.path.join(FONT_DIR, 'Font.ttc'), 22)
font30 = ImageFont.truetype(os.path.join(FONT_DIR, 'Font.ttc'), 30)
font35 = ImageFont.truetype(os.path.join(FONT_DIR, 'Font.ttc'), 35)
font50 = ImageFont.truetype(os.path.join(FONT_DIR, 'Font.ttc'), 50)
font60 = ImageFont.truetype(os.path.join(FONT_DIR, 'Font.ttc'), 60)
font160 = ImageFont.truetype(os.path.join(FONT_DIR, 'Font.ttc'), 160)

# PIL uses standard RGB or 1-bit values
COLOR_BLACK = 0
COLOR_WHITE = 255


def fetch_weather_data():
    """Fetches data from OpenWeatherMap API."""
    url = f"{BASE_URL}?lat={LATITUDE}&lon={LONGITUDE}&units={UNITS}&appid={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        logging.info("Weather data fetched successfully.")
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Failed to fetch weather data: {e}")
        raise

def process_weather_data(data):
    """Extracts only the required data from the API response."""
    try:
        current = data['current']
        daily = data['daily'][0]
        weather_data = {
            "temp_current": current['temp'],
            "feels_like": current['feels_like'],
            "humidity": current['humidity'],
            "wind": current['wind_speed'],
            "report": current['weather'][0]['description'].title(),
            "icon_code": current['weather'][0]['icon'],
            "temp_max": daily['temp']['max'],
            "temp_min": daily['temp']['min'],
            "precip_percent": daily['pop'] * 100,
        }
        logging.info("Weather data processed successfully.")
        return weather_data
    except KeyError as e:
        logging.error(f"Error processing weather data: {e}")
        raise

def generate_display_image(weather_data):
    """Draws text and icons onto the template."""
    try:
        # Note: Your template.png MUST be exactly 800x480 pixels for this display.
        template_path = os.path.join(PIC_DIR, 'template.png')
        if not os.path.exists(template_path):
            logging.warning("template.png not found. Creating a blank white background.")
            template = Image.new('1', (800, 480), COLOR_WHITE)
        else:
            # Open template and ensure it is in 1-bit color mode
            template = Image.open(template_path).convert('1')
            
        draw = ImageDraw.Draw(template)
        
        # Draw Icon
        icon_path = os.path.join(ICON_DIR, f"{weather_data['icon_code']}.png")
        if os.path.exists(icon_path):
            icon_image = Image.open(icon_path).convert('1')
            template.paste(icon_image, (40, 15))
        else:
            logging.warning(f"Weather icon {weather_data['icon_code']}.png not found.")

        # Draw Text Data
        draw.text((30, 200), f"Now: {weather_data['report']}", font=font22, fill=COLOR_BLACK)
        draw.text((30, 240), f"Precip: {weather_data['precip_percent']:.0f}%", font=font30, fill=COLOR_BLACK)
        draw.text((375, 35), f"{weather_data['temp_current']:.0f}°C", font=font160, fill=COLOR_BLACK)
        draw.text((350, 210), f"Feels like: {weather_data['feels_like']:.0f}°C", font=font50, fill=COLOR_BLACK)
        draw.text((35, 325), f"High: {weather_data['temp_max']:.0f}°C", font=font50, fill=COLOR_BLACK)
        draw.text((35, 390), f"Low: {weather_data['temp_min']:.0f}°C", font=font50, fill=COLOR_BLACK)
        draw.text((345, 340), f"Humidity: {weather_data['humidity']}%", font=font30, fill=COLOR_BLACK)
        draw.text((345, 400), f"Wind: {weather_data['wind']:.1f} m/s", font=font30, fill=COLOR_BLACK)
        
        # Draw Update Time
        draw.text((627, 330), "UPDATED", font=font35, fill=COLOR_WHITE) # Assuming background here is black
        current_time = datetime.now().strftime('%H:%M')
        draw.text((627, 375), current_time, font=font60, fill=COLOR_WHITE)
        
        logging.info("Display image generated successfully.")
        return template
    except Exception as e:
        logging.error(f"Error generating display image: {e}")
        raise

def display_image(black_image):
    """Sends the image buffer to the E-Paper display and puts it to sleep."""
    try:
        logging.info("Initializing E-Paper display...")
        epd = epd7in5b_V2.EPD()
        epd.init()
        epd.Clear()

        # The 'B' display requires a second image buffer for the RED pixels.
        # Since we aren't using red, we pass a blank white image.
        red_image = Image.new('1', (epd.width, epd.height), COLOR_WHITE)

        logging.info("Sending image to screen (this takes ~15-20 seconds)...")
        epd.display(epd.getbuffer(black_image), epd.getbuffer(red_image))
        
        # CRITICAL: Put the display to sleep to prevent voltage damage to the glass
        logging.info("Putting display to sleep.")
        epd.sleep()
        
    except Exception as e:
        logging.error(f"Failed to display image: {e}")
        raise

def main():
    try:
        logging.info("--- Weather Script Started ---")
        raw_data = fetch_weather_data()
        weather_data = process_weather_data(raw_data)
        black_image = generate_display_image(weather_data)
        display_image(black_image)
        logging.info("--- Weather Script Finished Successfully ---")
        
    except Exception as e:
        logging.error(f"An unexpected error occurred in main loop: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()