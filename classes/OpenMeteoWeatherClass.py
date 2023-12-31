#FORECASTS
import openmeteo_requests

import pandas as pd
from datetime import datetime, timedelta
from retry_requests import retry

from classes.ConfigManagerClass import ConfigManager
from classes.GCS import GCSManager

from classes.LoggingClass import LoggingManager

runtime_logger_level = 'DEBUG'

class WeatherHistoryRetriever:
    def __init__(self):
        # Setup the Open-Meteo API client with cache and retry on error
        #cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
        #retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        #self.openmeteo = openmeteo_requests.Client(session=retry_session)
        self.openmeteo = openmeteo_requests.Client()

        # Setup Config manager and GCS client
        self.config = ConfigManager(yaml_filepath='config', yaml_filename='config.yaml')
        self.gcs_manager = GCSManager()

        self.date_today = datetime.now().strftime('%Y-%m-%d')

        self.logger = LoggingManager.create_logger(
            self,
            logger_name='OpenMeteoWeatherClass.py',
            debug_level=runtime_logger_level
        )

    # def _fetch_hourly_data(self, latitude, longitude, start_date, end_date, name):
    #     # Fetch the response
    #     url = "https://archive-api.open-meteo.com/v1/archive"
    #     params = {
    #         "latitude": latitude,
    #         "longitude": longitude,
    #         "start_date": start_date,
    #         "end_date": end_date,
    #         "hourly": ["temperature_2m", "relative_humidity_2m", "apparent_temperature", "precipitation", "rain", "snowfall", "wind_speed_10m"]
    #     }
    #     responses = self.openmeteo.weather_api(url, params=params)

    #     # Process the response
    #     response = responses[0]
    #     self.logger.info(responses[0])
    #     hourly = response.Hourly(hourly)
        
    #     self.logger.info(hourly)
    #     return hourly

    def fetch_and_process(self, latitude, longitude, start_date, end_date, name):
        # Fetch the response
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ["temperature_2m", "relative_humidity_2m", "apparent_temperature", "precipitation", "rain", "snowfall", "wind_speed_10m"]
        }
        responses = self.openmeteo.weather_api(url, params=params)

        # Process the response
        response = responses[0]
        hourly = response.Hourly()
        hourly_data = self._process_hourly_data(hourly, name)

        return pd.DataFrame(data=hourly_data)

    def _process_hourly_data(self, hourly, name):
        # Original columns from the function
        variable_names = ["temperature_2m", "relative_humidity_2m", "apparent_temperature", "precipitation", "rain", "snowfall", "wind_speed_10m"]
        variables = [hourly.Variables(i).ValuesAsNumpy() for i in range(len(variable_names))]
        
        # Create a dictionary for the data with new column names aligned with forecast_schema
        hourly_data = {
            "forecast_datetime": pd.date_range(
                start=pd.to_datetime(hourly.Time(), unit="s"),
                end=pd.to_datetime(hourly.TimeEnd(), unit="s"),
                freq=pd.Timedelta(seconds=hourly.Interval()),
                inclusive="left"
            ),
            "temp": variables[0],  # Assuming temperature_2m corresponds to temp
            "temp_humidity": variables[1],  # Assuming relative_humidity_2m corresponds to temp_humidity
        }

        # Make df and add colukmns
        df = pd.DataFrame(data=hourly_data)
        df['name'] = name
        df['weather_date'] = df['forecast_datetime'].dt.date

        # Filter out rows where the hour is not divisible by 3 and order cols
        df = df[df['forecast_datetime'].dt.hour % 3 == 0]
        df = df[['weather_date', 'forecast_datetime','temp','temp_humidity','name']]
        
        self.logger.info("df.dtypes: ")
        self.logger.info(df.dtypes)
        return df

# Example usage
if __name__ == "__main__":
    #TEST1   
    config = ConfigManager(yaml_filepath='config', yaml_filename='config.yaml')
    gcs_manager = GCSManager()
    wthr_history_retriever = WeatherHistoryRetriever()
    date_today = datetime.now().strftime('%Y-%m-%d')
    users_details = config.users_details

    dfs = []

    six_days_ago = (datetime.now() - timedelta(days=6)).strftime('%Y-%m-%d')
    start_date = six_days_ago
    end_date = six_days_ago

    for user in users_details:
        name = user['name']
        lat = user['lat']
        lon = user['lon']
        print(f"Fetching data for {name}...")
        df = wthr_history_retriever.fetch_and_process(lat, lon, start_date, end_date, name)
        dfs.append(df)
    
    df_unioned = pd.concat(dfs, ignore_index=True)
    print(df_unioned.head(5))
