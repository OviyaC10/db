import pandas as pd
import gspread as gs
from google.oauth2.service_account import Credentials
from flask import Flask, render_template, request
from flask_restful import Api
import plotly.express as px
import openai
from flask import jsonify
import os 
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
# Flask app setup
app = Flask(__name__)
api = Api(app)

# Google Sheets setup
scopes = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gs.authorize(creds)

# Load first Google Sheet (existing df)
sheet_id_1 = '1M5r9nur77ztePFtZebZJ3MwVCKhnZemE4zvNvglqrlQ'
sheet_1 = client.open_by_key(sheet_id_1)
data_1 = sheet_1.sheet1.get_all_values()
df = pd.DataFrame(data_1[1:], columns=data_1[0])
df.columns = df.columns.str.strip()  # Strip extra spaces from column names

# Load second Google Sheet (df1)
sheet_id_2 = '1dPUSoKZU5H_ygtSmWevdD1Xyy7NloMMRztiaSpqsJ4Q'
sheet_2 = client.open_by_key(sheet_id_2)
data_2 = sheet_2.sheet1.get_all_values()
df1 = pd.DataFrame(data_2[1:], columns=data_2[0])
df1.columns = df1.columns.str.strip()  # Strip extra spaces from column names



openai.api_key = os.getenv('OPENAI_API_KEY')


@app.route('/get_response', methods=['POST'])
def get_openai_response():
    user_message = "For each startup in the sheet: Review the goals  and compare it to the achievements and more_achievements listed.For each goal, check if it was accomplished or still pending.Provide a clear and concise table with the goals and their status for each week.\n"
    
    # Loop through each row in the DataFrame (df1)
    for index, row in df1.iterrows():
        Startup_Name = row['Startup Name']
        week = row['Week #']
        goals = row['Goals for Next Week\nWhat are your top goals for the coming week?']
        achievements = row["Product Milestones\nDid you reach any product milestones this week (e.g., prototype, demo, or feature release)?Please describe the milestone and its significance to the product's development."]
        more_achievements = row['More\nAny other significant milestones achieved, events, meet new people?']
        
        # Append data for OpenAI's analysis
        user_message += f"Startup Name: {Startup_Name} Week {week}: Goals: {goals}, Achievements: {achievements}, More Achievements: {more_achievements}\n"

    # Make the OpenAI request
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "system", "content": "You are a helpful assistant designed to analyze and process startup progress data. Your task is to review weekly updates provided by the startup team, identify the goals for the upcoming week, and determine whether each goal was achieved or is yet to be achieved. For each week, you will output a table summarizing the status of each goal, marking it as 'Achieved' or 'Yet to achieve' based on the provided achievements."},
                  {"role": "user", "content": user_message}],
        temperature=0.7,
        max_tokens=2048
    )
    text_response = response['choices'][0]['message']['content']

    # Parse the markdown table from the OpenAI response
    parsed_data = parse_markdown_table(text_response)

    # If data was parsed, convert to DataFrame
    if parsed_data:
        df_res = pd.DataFrame(parsed_data)
        return jsonify({"response": df_res.to_html(classes='table table-striped')})
    else:
        return jsonify({"response": "No data was parsed. Please check the input format."})

def parse_markdown_table(text):
    # Split the text into lines and clean up spaces
    lines = text.strip().split("\n")
    
    # The first line is the header row
    header = [col.strip() for col in lines[0].strip("|").split("|")]
    
    # Extract the rows to be parsed (skip the separator line)
    rows = lines[2:]

    # Parse each row into a dictionary
    parsed_data = []
    for row in rows:
        columns = [col.strip() for col in row.strip("|").split("|")]
        if len(columns) == len(header):  # Ensure that the number of columns matches the header
            parsed_data.append({header[i]: columns[i] for i in range(len(header))})
    
    return parsed_data


# Routes
@app.route('/')
def index():
    # Validate if the necessary column exists before accessing it
    if "Team's name/ mentor" not in df.columns:
        return "Error: Column 'Team's name/ mentor' not found in the data.", 500

    # Pass unique team names to populate the dropdown for the first graph
    teams = df["Team's name/ mentor"].dropna().unique().tolist()

    # Pass unique startup names to populate the dropdown for the third graph
    startup_names = df1["Startup Name"].dropna().unique().tolist()

    return render_template('index.html', teams=teams, startup_names=startup_names)


@app.route('/visualize', methods=['POST'])
def visualize():
    selected_team = request.form.get('team')
    selected_startup = request.form.get('startup')


    if not selected_team:
        return "Error: No team selected.", 400

    # Filter data for the selected team
    filtered_df = df[df["Team's name/ mentor"] == selected_team]

    # Ensure required columns exist for the first chart (Insights)
    insights_columns = [
        "Please select the week in which you are providing feedback",
        "To what extent did you gain new insights from this week's workshop(s)?"
    ]
    if insights_columns[1] not in filtered_df.columns:
        return f"Error: Column '{insights_columns[1]}' not found in the data.", 500
    
    filtered_df[insights_columns[1]] = pd.to_numeric(filtered_df[insights_columns[1]], errors='coerce')

    # Create the first bar chart (Insights Gained)
    fig1 = px.bar(
        filtered_df,
        x=insights_columns[0],
        y=insights_columns[1],
        title=f"Insights Gained for {selected_team}",
        labels={insights_columns[0]: "Week", insights_columns[1]: "Insights"}
    )

    # Create the second bar chart (Recommendation Likelihood)
    recommendation_columns = [
        "Please select the week in which you are providing feedback",
        "Based on this week's workshop(s), how likely would you recommend the Cohort Program to other founders, entrepreneurs, and innovators."
    ]
    if recommendation_columns[1] not in filtered_df.columns:
        return f"Error: Column '{recommendation_columns[1]}' not found in the data.", 500
    
    filtered_df[recommendation_columns[1]] = pd.to_numeric(filtered_df[recommendation_columns[1]], errors='coerce')

    fig2 = px.bar(
        filtered_df,
        x=recommendation_columns[0],
        y=recommendation_columns[1],
        title=f"Recommendation Likelihood for {selected_team}",
        labels={recommendation_columns[0]: "Week", recommendation_columns[1]: "Recommendation Likelihood"}
    )

    # Filter data for the selected startup for the third graph
    filtered_df1 = df1[df1["Startup Name"] == selected_startup]

    # Ensure the columns exist for the third chart (Revenue vs. Week)
    revenue_columns = ["Week #", "Revenue generated?"]
    if revenue_columns[1] not in filtered_df1.columns:
        return f"Error: Column '{revenue_columns[1]}' not found in the data.", 500
    
    filtered_df1[revenue_columns[1]] = pd.to_numeric(filtered_df1[revenue_columns[1]], errors='coerce')

    # Create the third bar chart (Revenue Generated)
    fig3 = px.bar(
        filtered_df1,
        x=revenue_columns[0],
        y=revenue_columns[1],
        title=f"Revenue Generated for {selected_startup}",
        labels={revenue_columns[0]: "Week", revenue_columns[1]: "Revenue Generated"}
    )


    # Render all charts as HTML
    graph1_html = fig1.to_html(full_html=False)
    graph2_html = fig2.to_html(full_html=False)
    graph3_html = fig3.to_html(full_html=False)

    return f"""
    <div>
        <h2>Insights Gained</h2>
        {graph1_html}
    </div>
    <div>
        <h2>Recommendation Likelihood</h2>
        {graph2_html}
    </div>
    <div>
        <h2>Revenue Generated</h2>
        {graph3_html}
    </div>
    """


if __name__ == "__main__":
    app.run(host='127.0.0.1', port=5000, debug=True)