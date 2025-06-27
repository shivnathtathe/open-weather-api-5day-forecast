import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
import httpx

# Load API key
load_dotenv()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
print("Using API Key:", OPENWEATHER_API_KEY)

app = FastAPI(title="5-Day Weather Forecast API")

# ----------- Models -----------
class PlaceListRequest(BaseModel):
    places: List[str]
    action: Literal["basic", "detailed"] = Field(default="basic", description="Type of forecast: 'basic' or 'detailed'")

class BasicDailyForecast(BaseModel):
    date: str
    min_temp_c: float
    max_temp_c: float
    precipitation_mm: float

class DetailedDailyForecast(BasicDailyForecast):
    avg_temp_c: float
    humidity_percent: float
    wind_speed_mps: float
    weather_desc: str
    weather_icon: str

class PlaceForecast(BaseModel):
    place: str
    daily_forecast: List[BasicDailyForecast | DetailedDailyForecast]

class ForecastResponse(BaseModel):
    forecasts: List[PlaceForecast]

# ----------- Logic -----------
async def fetch_forecast(place: str, action: str) -> PlaceForecast:
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

    daily_data = defaultdict(list)
    for entry in data["list"]:
        dt = datetime.fromtimestamp(entry["dt"]).date().isoformat()
        daily_data[dt].append(entry)

    forecast = []
    for dt in sorted(daily_data.keys())[:5]:
        entries = daily_data[dt]
        min_temp = min(e["main"]["temp_min"] for e in entries)
        max_temp = max(e["main"]["temp_max"] for e in entries)
        precipitation = sum(e.get("rain", {}).get("3h", 0.0) for e in entries)

        if action == "basic":
            forecast.append(BasicDailyForecast(
                date=dt,
                min_temp_c=round(min_temp, 1),
                max_temp_c=round(max_temp, 1),
                precipitation_mm=round(precipitation, 1)
            ))
        else:
            avg_temp = sum((e["main"]["temp_min"] + e["main"]["temp_max"]) / 2 for e in entries) / len(entries)
            humidity = sum(e["main"]["humidity"] for e in entries) / len(entries)
            wind_speed = sum(e["wind"]["speed"] for e in entries) / len(entries)
            descriptions = [e["weather"][0]["description"] for e in entries]
            icons = [e["weather"][0]["icon"] for e in entries]
            common_desc = max(set(descriptions), key=descriptions.count)
            common_icon = max(set(icons), key=icons.count)

            forecast.append(DetailedDailyForecast(
                date=dt,
                min_temp_c=round(min_temp, 1),
                max_temp_c=round(max_temp, 1),
                avg_temp_c=round(avg_temp, 1),
                precipitation_mm=round(precipitation, 1),
                humidity_percent=round(humidity),
                wind_speed_mps=round(wind_speed, 1),
                weather_desc=common_desc,
                weather_icon=common_icon
            ))

    return PlaceForecast(place=place, daily_forecast=forecast)

# ----------- Endpoint -----------
@app.post("/api/v1/WeatherForecastByPlacesList", response_model=ForecastResponse)
async def get_weather_forecast(request: PlaceListRequest):
    if not request.places:
        raise HTTPException(status_code=400, detail="The 'places' list cannot be empty.")

    results = []
    for place in request.places:
        forecast = await fetch_forecast(place, request.action)
        results.append(forecast)

    return ForecastResponse(forecasts=results)
