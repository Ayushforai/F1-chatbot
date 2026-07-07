import kagglehub
import shutil
import os

def setup_kaggle_data():
    print("Downloading historical F1 dataset from Kaggle...")
    # This downloads the dataset to a hidden cache folder on your Mac
    path = kagglehub.dataset_download("rohanrao/formula-1-world-championship-1950-2020")
    
    # We want to move it into your project's data folder
    target_dir = "./data/historical_csvs"
    os.makedirs(target_dir, exist_ok=True)
    
    # Move all downloaded CSVs to our project directory
    for file_name in os.listdir(path):
        full_file_name = os.path.join(path, file_name)
        if os.path.isfile(full_file_name):
            shutil.copy(full_file_name, target_dir)
            
    print(f"Success! Historical CSVs are now stored locally in: {target_dir}")

if __name__ == "__main__":
    setup_kaggle_data()