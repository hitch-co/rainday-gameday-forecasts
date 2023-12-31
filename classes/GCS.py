import pandas as pd
import io
import os

from google.cloud import bigquery
from google.cloud import storage
from google.cloud.exceptions import NotFound

from classes.LoggingClass import LoggingManager
from classes.ConfigManagerClass import ConfigManager

runtime_logger_level = 'INFO'

class GCSManager:

    def __init__(self):
        self.config = ConfigManager(yaml_filename='config.yaml', yaml_filepath='config')
        self.logging_manager = LoggingManager()
        self.logger = self.logging_manager.create_logger(
            logger_name='log_GCS', 
            debug_level=runtime_logger_level,
            mode='a',
            stream_logs=True,
            encoding='UTF-8'
            )
        self.bq_client = bigquery.Client()
        self.gcs_client = storage.Client()

    # list all files/directories/blobs
    def list_gcs_blobs(self, bucket_name = 'rainday-gameday-bucket'):
        blobs = self.gcs_client.list_blobs(bucket_name)
        blobs_list = list(blobs)
        self.logger.info('func list_gcs_blobs: finished')
        return blobs_list

    # Union blobs 
    def union_gcs_csv_blobs(
            self,
            blobs_list, 
            csvs_to_union_folder_location=''
            ):
        dfs = [] 
        self.logger.info("started union_gcs_csv_blobs")
        self.logger.info(f"This is the csvs_to_union_folder_location: {csvs_to_union_folder_location}")
        self.logger.debug("This is the blobslist:")
        self.logger.debug(blobs_list)

        for blob in blobs_list:
            self.logger.debug("This is the blob")
            self.logger.debug(blob)
            
            if blob.name.startswith(csvs_to_union_folder_location) and blob.name.endswith('.csv') and not blob.name.endswith('/'):
                csv_content = io.StringIO() 
                csv_content.write(blob.download_as_text())
                csv_content.seek(0)
                df = pd.read_csv(csv_content)
                
                self.logger.debug("THIS IS THE df INSIDE OF union_gcs_csv_blobs loop:")
                self.logger.debug(df)
                
                dfs.append(df)

                self.logger.debug("THIS IS THE dfs INSIDE OF union_gcs_csv_blobs loop:")
                self.logger.debug(dfs)

        unioned_dfs = pd.concat(dfs, ignore_index=True)
        self.logger.info("This is the FINAL df")
        self.logger.info(unioned_dfs.head(5))

        self.logger.info('func union_gcs_csv_blobs: finished')
        return unioned_dfs

    def download_all_files_in_gcs_folder(self, bucket_name, folder_path, destination_folder):
        # Create the destination folder if it doesn't exist
        if not os.path.exists(destination_folder):
            os.makedirs(destination_folder)

        # Get the bucket
        bucket = self.gcs_client.bucket(bucket_name)

        # List all blobs in the specified folder
        blobs = bucket.list_blobs(prefix=folder_path)
        self.logger.info("THIS IS THE BLOBS LIST")
        self.logger.info(blobs)
        # Download each file
        for blob in blobs:
            # Extract the file name from the blob name
            file_name = blob.name.replace(folder_path, '')
                    
            # Skip if it's a directory placeholder (ends with '/')
            if not file_name or file_name.endswith('/'):
                continue

            # Set the destination path
            destination_path = os.path.join(destination_folder, file_name)

            # Download the file
            blob.download_to_filename(destination_path)
            print(f"Downloaded {blob.name} to {destination_path}")

    #Creates big query table from GCS blob
    def create_bq_table_from_gcs(self,
                            project_name = 'your-project-name', 
                            bucket_name = 'your-bucket-name' ,
                            dataset_name = 'rainday-gameday-models', 
                            target_table_name = 'your_new_table_name',
                            source_file_path = 'file_location_for_new_table',
                            is_testing_run = False):
        """
        Creates a BigQuery table from a CSV file in Google Cloud Storage (GCS) if the table does not already exist.

        Args:
            project_name (str): The ID of the Google Cloud project.
            dataset_name (str): The ID of the BigQuery dataset within the project.
            target_table_name (str): The name of the BigQuery table to be created within the dataset.
            source_file_path (str): The name of the google cloud storage source file to create the dataset
            bucket_name (str): The name of the GCS bucket where the CSV file is stored.
            source_file_path (str): The path to the CSV file in the GCS bucket.

        Example:
            create_table_from_gcs('your-project', 'your-dataset', 'your-table', 'rainday-gameday-bucket', 'forecast_history_csv/all_historic_forecasts.csv')

        More info:
        - BigQuery Python Client Library: https://cloud.google.com/bigquery/docs/reference/libraries#client-libraries-usage-python
        - Google Cloud Storage: https://cloud.google.com/storage
        """

        # Define the GCS URI.
        uri = "gs://{}/{}".format(bucket_name, source_file_path)

        # Define the expected schema incase a table is not found 
        schema = [
            bigquery.SchemaField("forecast_capture_date", "STRING"),
            bigquery.SchemaField("forecast_dateunix", "STRING"), #FLOAT
            bigquery.SchemaField("forecast_datestring", "STRING"),
            bigquery.SchemaField("name", "STRING"),
            bigquery.SchemaField("rain_category", "STRING"),
            bigquery.SchemaField("rain_category_value", "STRING"), #INTEGER
            bigquery.SchemaField("temp", "STRING"), #FLOAT64
            bigquery.SchemaField("temp_min", "STRING"), #FLOAT64
            bigquery.SchemaField("temp_max", "STRING"), #FLOAT64
            bigquery.SchemaField("temp_humidity", "STRING"), #FLOAT64
            bigquery.SchemaField("weather_class", "STRING"),
            bigquery.SchemaField("weather_description", "STRING"),
        ]

        # Set the full table reference, which includes the project ID, dataset ID, and table name.
        table_fullqual = "{}.{}.{}".format(project_name, dataset_name, target_table_name)
        table_ref = bigquery.TableReference.from_string(table_fullqual)
        type(table_ref)
        type(table_fullqual)

        # Check if the table already exists.
        try:
            self.bq_client.get_table(table_ref)
            self.logger.info(f"Table {table_fullqual} already exists.")
        except NotFound:
            self.logger.info(f"Table {table_fullqual} is not found.\n Creating new table")

            # Use the client to create a new table.
            table = bigquery.Table(table_ref, schema=schema)
            table = self.bq_client.create_table(table)  # Make an API request.
            self.logger.info(f"Table {table_fullqual} created.")

        # Configure the external data source and start the BigQuery Load job.
        job_config = bigquery.LoadJobConfig(
            autodetect=False,
            schema=schema,
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
        )
        load_job = self.bq_client.load_table_from_uri(uri, table_ref, job_config=job_config)

        # Wait for the job to complete.
        load_job_result = load_job.result()
        self.logger.info(load_job_result)
        return self.logger.info(load_job_result)

    #Reads GCS blob and writes to local file
    #TODO: NOT WORKING
    def get_config_from_gcs_csv(self,
                                bucket_name = 'your_bucket_name', 
                                gcs_bucket_blobdir = 'your\\blob\\directory',
                                gcs_blob_name = 'your-blob_name.csv',
                                is_testing_run=False):
        
        bucket_name = 'rainday-gameday-bucket'
        gcs_bucket_blobdir = 'forecast_history_csv'
        gcs_blob_name = 'all_historic_forecasts.csv'

        #set/create variables
        gcs_blobpath = os.path.join(gcs_bucket_blobdir, gcs_blob_name)

        # get the bucket that the file will be uploaded to.
        bucket_object = self.gcs_client.get_bucket(bucket_name)

        # Create a new local blob and download file to local directory
        fileblob_object = bucket_object.blob(gcs_blobpath)
        
        gcs_blobpath = 'forecast_history_csv//all_historic_forecasts.csv'
        fileblob_object.download_to_filename(gcs_blobpath)
        
        #read xlsx for return
        df = pd.read_csv(gcs_blob_name)
        
        if 'a' != 'a':
            message = ''
        else:
            message = f"Retrieved {self.config.bucket_name} at location {gcs_bucket_blobdir} to dataframe" 
        print(message)
        return(df)

    #TODO: upload updated config located in root directory (move to different location?)
    def upload_config_to_gcs_xlsx(
            self,
            gcs_bucket_blobpath='your/bucket/blobpath.xlsx',
            is_testing_run=False
            ):
        bucket_object = self.gcs_client.get_bucket(self.config.bucket_name)
        print('TODO: incomplete, currently uploading manually')
        return()

    #Writes dataframe to specified bucket/path
    def write_df_to_gcs(self,
                        df, 
                        bucket_name = 'your_bucket_name', 
                        gcs_bucket_filepath = 'your/buckjet/filepath.csv', 
                        is_testing_run=False):

        if is_testing_run == True:
            df = pd.DataFrame(data=[[1,2,3],[4,5,6]],columns=['a','b','c'])

        # get the bucket that the file will be uploaded to.
        bucket_object = self.gcs_client.get_bucket(bucket_name)

        # Create a new blob and upload the file's content.
        fileblob_object = bucket_object.blob(gcs_bucket_filepath)

        # create/open and then write df to file object
        file_object = io.StringIO()
        df.to_csv(file_object, index=False)
        file_object.seek(0) #move to beginning for using read() below

        # upload from string and close file
        fileblob_object.upload_from_string(file_object.read(), content_type="text/csv")
        file_object.close()
        
        #error checking
        if 'a' != 'a':
            message = ''
        else:
            message = f"func write_df_to_gcs: finished\n  - Wrote to {bucket_name} at location {gcs_bucket_filepath}"     
        return(message)
    
def main():
    gcs_manager = GCSManager()
    gcs_blobs_list = gcs_manager.list_gcs_blobs(bucket_name='rainday-gameday-bucket')
    return gcs_blobs_list

if __name__ == '__main__':
    gcs_blobs_list = main()
    print(gcs_blobs_list)

