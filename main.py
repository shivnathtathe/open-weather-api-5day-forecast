import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
import httpx

# Load the OpenWeather API key
load_dotenv()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
print(OPENWEATHER_API_KEY)
app = FastAPI(title="5-Day Weather Forecast API")

# ----------- Models -----------
class PlaceListRequest(BaseModel):
    places: List[str]

class DailyForecast(BaseModel):
    date: str
    min_temp_c: float
    max_temp_c: float
    precipitation_mm: float

class PlaceForecast(BaseModel):
    place: str
    daily_forecast: List[DailyForecast]

class ForecastResponse(BaseModel):
    forecasts: List[PlaceForecast]

# ----------- Logic -----------
async def fetch_forecast(place: str) -> PlaceForecast:
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "q": place,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            detail = response.json().get("message", "Unknown error")
            raise HTTPException(status_code=response.status_code, detail=f"{place}: {detail}")

        data = response.json()

    # Aggregate 3-hour intervals into daily summaries
    daily_summary = defaultdict(lambda: {"min": float("inf"), "max": float("-inf"), "precip": 0.0})

    for entry in data["list"]:
        dt = datetime.fromtimestamp(entry["dt"]).date().isoformat()
        temp_min = entry["main"]["temp_min"]
        temp_max = entry["main"]["temp_max"]
        precipitation = entry.get("rain", {}).get("3h", 0.0)

        daily_summary[dt]["min"] = min(daily_summary[dt]["min"], temp_min)
        daily_summary[dt]["max"] = max(daily_summary[dt]["max"], temp_max)
        daily_summary[dt]["precip"] += precipitation

    
    forecast = []
    for dt in sorted(daily_summary.keys())[:5]:
        f = daily_summary[dt]
        forecast.append(DailyForecast(
            date=dt,
            min_temp_c=round(f["min"], 1),
            max_temp_c=round(f["max"], 1),
            precipitation_mm=round(f["precip"], 1)
        ))

    return PlaceForecast(place=place, daily_forecast=forecast)

# ----------- API Endpoint -----------
@app.post("/api/v1/WeatherForecastByPlacesList", response_model=ForecastResponse)
async def get_weather_forecast(request: PlaceListRequest):
    if not request.places:
        raise HTTPException(status_code=400, detail="The 'places' list cannot be empty.")

    results = []
    for place in request.places:
        forecast = await fetch_forecast(place)
        results.append(forecast)

    return ForecastResponse(forecasts=results)
