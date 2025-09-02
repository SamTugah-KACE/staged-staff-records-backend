# sample_files_generator.py
import pandas as pd
import numpy as np

# Explicitly import xlwt to register its Excel writer for .xls files.
try:
    import xlwt
except ImportError:
    print("xlwt not installed. Please run: pip install xlwt")

def generate_csv_file(filename="sample_bulk_upload.csv", num_rows=200):
    # Use 'ME' (month end) instead of deprecated 'M'
    df = pd.DataFrame({
         "first_name": np.random.choice(["Alice", "Bob", "Carol", "Dave"], size=num_rows),
         "middle_name": np.random.choice(["", "J.", "K.", "L."], size=num_rows),
         "last_name": np.random.choice(["Smith", "Johnson", "Williams", "Brown"], size=num_rows),
         "email": [f"user{i}@example.com" for i in range(num_rows)],
         "date_of_birth": pd.date_range(start="1970-01-01", periods=num_rows, freq="ME").strftime("%Y-%m-%d"),
         "hire_date": pd.date_range(start="2020-01-01", periods=num_rows, freq="D").strftime("%Y-%m-%d"),
         "department": np.random.choice(["HR", "IT", "Finance", "Marketing"], size=num_rows),
         "custom_field": np.random.randint(1, 100, size=num_rows)
    })
    df.to_csv(filename, index=False)
    print(f"CSV file generated: {filename}")

def generate_xlsx_file(filename="sample_bulk_upload_multiple.xlsx", num_rows=300):
    # Sheet 1: Employees
    df_employee = pd.DataFrame({
         "first_name": np.random.choice(["Alice", "Bob", "Carol", "Dave"], size=num_rows),
         "middle_name": np.random.choice(["", "J.", "K.", "L."], size=num_rows),
         "last_name": np.random.choice(["Smith", "Johnson", "Williams", "Brown"], size=num_rows),
         "email": [f"user{i}@example.com" for i in range(num_rows)],
         "hire_date": pd.date_range(start="2020-01-01", periods=num_rows, freq="D").strftime("%Y-%m-%d"),
         "department": np.random.choice(["HR", "IT", "Finance", "Marketing"], size=num_rows)
    })
    # Sheet 2: Academic Qualifications
    df_academic = pd.DataFrame({
         "degree": np.random.choice(["BSc", "MSc", "PhD"], size=num_rows),
         "institution": np.random.choice(["University A", "University B", "University C"], size=num_rows),
         "year_obtained": np.random.randint(1990, 2020, size=num_rows)
    })
    # Use openpyxl for writing XLSX files (ensure openpyxl is installed)
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
         df_employee.to_excel(writer, sheet_name="Employees", index=False)
         df_academic.to_excel(writer, sheet_name="AcademicQualifications", index=False)
    print(f"XLSX file generated: {filename}")

def generate_xls_file(filename="sample_bulk_upload.xls", num_rows=150):
    # Single-sheet XLS file with employee data
    df = pd.DataFrame({
         "first_name": np.random.choice(["Alice", "Bob", "Carol", "Dave"], size=num_rows),
         "last_name": np.random.choice(["Smith", "Johnson", "Williams", "Brown"], size=num_rows),
         "email": [f"user{i}@example.com" for i in range(num_rows)],
         "hire_date": pd.date_range(start="2020-01-01", periods=num_rows, freq="D").strftime("%Y-%m-%d"),
         "department": np.random.choice(["HR", "IT", "Finance", "Marketing"], size=num_rows)
    })
    try:
        with pd.ExcelWriter(filename, engine='xlwt') as writer:
            df.to_excel(writer, index=False)
        print(f"XLS file generated: {filename}")
    except ValueError as e:
        print("Error using xlwt:", e)
        # Fallback: Generate an XLSX file instead if xlwt isn't available.
        new_filename = filename.replace(".xls", ".xlsx")
        with pd.ExcelWriter(new_filename, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        print(f"Falling back: XLSX file generated: {new_filename}")

if __name__ == "__main__":
    generate_csv_file()
    generate_xlsx_file()
    generate_xls_file()




# # sample_files_generator.py
# import pandas as pd
# import numpy as np

# def generate_csv_file(filename="sample_bulk_upload.csv", num_rows=200):
#     # Sample employee data with dynamic extra column ("custom_field")
#     # Use frequency alias 'ME' (Month End) instead of 'M'
#     df = pd.DataFrame({
#          "first_name": np.random.choice(["Alice", "Bob", "Carol", "Dave"], size=num_rows),
#          "middle_name": np.random.choice(["", "J.", "K.", "L."], size=num_rows),
#          "last_name": np.random.choice(["Smith", "Johnson", "Williams", "Brown"], size=num_rows),
#          "email": [f"user{i}@example.com" for i in range(num_rows)],
#          "date_of_birth": pd.date_range(start="1970-01-01", periods=num_rows, freq="ME").strftime("%Y-%m-%d"),
#          "hire_date": pd.date_range(start="2020-01-01", periods=num_rows, freq="D").strftime("%Y-%m-%d"),
#          "department": np.random.choice(["HR", "IT", "Finance", "Marketing"], size=num_rows),
#          "custom_field": np.random.randint(1, 100, size=num_rows)
#     })
#     df.to_csv(filename, index=False)
#     print(f"CSV file generated: {filename}")

# def generate_xlsx_file(filename="sample_bulk_upload_multiple.xlsx", num_rows=300):
#     # Sheet 1: Employees
#     df_employee = pd.DataFrame({
#          "first_name": np.random.choice(["Alice", "Bob", "Carol", "Dave"], size=num_rows),
#          "middle_name": np.random.choice(["", "J.", "K.", "L."], size=num_rows),
#          "last_name": np.random.choice(["Smith", "Johnson", "Williams", "Brown"], size=num_rows),
#          "email": [f"user{i}@example.com" for i in range(num_rows)],
#          "hire_date": pd.date_range(start="2020-01-01", periods=num_rows, freq="D").strftime("%Y-%m-%d"),
#          "department": np.random.choice(["HR", "IT", "Finance", "Marketing"], size=num_rows)
#     })
#     # Sheet 2: Academic Qualifications
#     df_academic = pd.DataFrame({
#          "degree": np.random.choice(["BSc", "MSc", "PhD"], size=num_rows),
#          "institution": np.random.choice(["University A", "University B", "University C"], size=num_rows),
#          "year_obtained": np.random.randint(1990, 2020, size=num_rows)
#     })
#     # Specify the engine explicitly; ensure openpyxl is installed: pip install openpyxl
#     with pd.ExcelWriter(filename, engine='openpyxl') as writer:
#          df_employee.to_excel(writer, sheet_name="Employees", index=False)
#          df_academic.to_excel(writer, sheet_name="AcademicQualifications", index=False)
#     print(f"XLSX file generated: {filename}")

# def generate_xls_file(filename="sample_bulk_upload.xls", num_rows=150):
#     # Single-sheet XLS file with employee data
#     df = pd.DataFrame({
#          "first_name": np.random.choice(["Alice", "Bob", "Carol", "Dave"], size=num_rows),
#          "last_name": np.random.choice(["Smith", "Johnson", "Williams", "Brown"], size=num_rows),
#          "email": [f"user{i}@example.com" for i in range(num_rows)],
#          "hire_date": pd.date_range(start="2020-01-01", periods=num_rows, freq="D").strftime("%Y-%m-%d"),
#          "department": np.random.choice(["HR", "IT", "Finance", "Marketing"], size=num_rows)
#     })
#     df.to_excel(filename, index=False)
#     print(f"XLS file generated: {filename}")

# if __name__ == "__main__":
#     generate_csv_file()
#     generate_xlsx_file()
#     generate_xls_file()
