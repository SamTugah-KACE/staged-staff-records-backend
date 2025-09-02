#!/bin/bash
echo "Running unit and integration tests..."
pytest --asyncio-mode=auto --maxfail=3 --durations=10 || { echo "Tests failed."; exit 1; }
pytest --cov=app --cov-report=html || { echo "Coverage report generation failed."; exit 1; }
echo "Tests completed successfully."

# echo "Tests completed successfully."
 
#  The  run_tests.sh  script is a simple bash script that runs the tests using the  pytest  command. The  --asyncio-mode=auto  flag is used to enable asyncio support in the tests. The  --maxfail=3  flag is used to stop the test run after 3 failures. The  --durations=10  flag is used to display the slowest 10 tests. The  --cov=app  flag is used to generate a coverage report for the app package. The  --cov-report=html  flag is used to generate an HTML coverage report. 
#  To run the tests, navigate to the  App  directory and run the  run_tests.sh  script: 
#  $ cd App
