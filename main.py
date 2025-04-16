from typing import Optional
from fastapi import FastAPI
import textdistance
import pandas as pd
# from template import conn,test_user,conn_params
from utils import *  # Use relative import if utils.py is in the same directory
import uvicorn
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, HTTPException, status
from pydantic import BaseModel
# import snowflake.connector
from fuzzywuzzy import fuzz
from input import country_sources
from datetime import date
import time
import sqlite3
# from snowflake.snowpark import Session

test_user = {
    "username": "testuser",
    "password": "affixcon1234"
}

app = FastAPI()

security = HTTPBasic()

class UserData(BaseModel):
    CountryPrefix: str
    IDNumber: Optional[str] = None
    FirstName: str
    MiddleName: str
    Surname: str
    Dob: str
    AddressElement1: str
    AddressElement2: str
    AddressElement3: str
    AddressElement4: str
    Mobile: str
    Email: str

def verify_credentials(credentials: HTTPBasicCredentials):
    if credentials.username == test_user["username"] and credentials.password == test_user["password"]:
        return {"username": credentials.username}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Basic"},
    )

@app.post("/verify_user/")
async def verify_user(data: UserData, credentials: HTTPBasicCredentials = Depends(security)):
    verify_credentials(credentials)
    
    start_time = time.time()

    connection = sqlite3.connect(f'artifacts\\{data.CountryPrefix}.db')

    # Create a cursor object
    cursor = connection.cursor()

    # Query to get the list of tables in the database
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")

    # Fetch the first table name
    table_name = cursor.fetchone()[0]

    try:
        # session = Session.builder.configs(conn_params).create()
        first_name_condition = build_match_conditions(data.FirstName.upper(), 'GIVEN_NAME_1','FULL_NAME') if data.FirstName else "0"
        middle_name_condition = build_match_conditions(data.MiddleName.upper(), 'GIVEN_NAME_2','FULL_NAME') if data.MiddleName else "0"
        sur_name_condition = build_match_conditions(data.Surname.upper(), 'SURNAME','FULL_NAME') if data.Surname else "0"

        if data.IDNumber:
            # query = f"""
            #     select * from PUBLIC.{country_sources[data.CountryPrefix]['table_name']} where lower(ID_CARD) = '{data.IDNumber.lower()}'
            #     """
            query = f"""
                select * from {table_name} where lower(ID_CARD) = '{data.IDNumber.lower()}'
                """
            
        else:
            query = f"""
            WITH matched_records AS (
            SELECT
                FULL_NAME,
                GIVEN_NAME_1,
                GIVEN_NAME_2,
                GIVEN_NAME_3,
                SURNAME,
                DOB_YYYYMMDD,
                DOB_YYYYMMDD_DATE,
                FULL_ADDRESS,
                AD1,
                SUB_DISTRICT,
                DISTRICT,
                CITY,
                REGENCY,
                PROVINCE,
                POSTCODE,
                MOBILE,
                EMAIL,
                {first_name_condition} AS first_name_score,
                {middle_name_condition} AS middle_name_score,
                {sur_name_condition} AS sur_name_score,


                CASE
                --     -- WHEN '{data.Dob}' != '' AND DOB_YYYYMMDD_DATE = '{data.Dob}'::DATE
                       WHEN '{data.Dob}' != '' AND DOB_YYYYMMDD_DATE = '{data.Dob}'

                    THEN 1.0
                    ELSE 0
                END AS dob_score
            FROM
                {table_name}
            )
            SELECT *
            FROM matched_records
            WHERE (first_name_score + middle_name_score + sur_name_score  +dob_score ) >= 2
            ORDER BY (first_name_score + middle_name_score + sur_name_score +dob_score ) DESC
            LIMIT 10;
            """

        # else:
        #     query = f"""select 
        #            FULL_NAME,
        #            GIVEN_NAME_1,
        #            GIVEN_NAME_2,
        #            GIVEN_NAME_3,
        #            SURNAME,
        #            DOB_YYYYMMDD,
        #            DOB_YYYYMMDD_DATE,
        #            FULL_ADDRESS,
        #            AD1,
        #            SUB_DISTRICT,
        #            DISTRICT,
        #            CITY,
        #            REGENCY,
        #            PROVINCE,
        #            POSTCODE,
        #            MOBILE,
        #            EMAIL,
        #            {first_name_condition} AS first_name_score,
        #            {middle_name_condition} AS middle_name_score,
        #            {sur_name_condition} AS sur_name_score,
        #            CASE
        #                WHEN '{data.Dob}' != '' AND DOB_YYYYMMDD_DATE = '{data.Dob}'
        #                THEN 1.0
        #                ELSE 0
        #            END AS dob_score
        #            from {table_name} limit 10;"""
        cursor.execute(query)
        rows = cursor.fetchall()

        # # Get column names from the cursor description
        columns = [description[0] for description in cursor.description]
        # # Create a DataFrame from the fetched rows and column names
        df = pd.DataFrame(rows, columns=columns)
        # df = session.sql(query).to_pandas()

        # end_time = time.time()

        # df['time']=int((end_time - start_time) * 1000)

        df_selected = df.head(1)
        df = df.fillna("").replace('<NA>','').reset_index(drop=True)
    
        if df.empty:
            raise HTTPException(status_code=404, detail="No match found")
    

        full_name_input = data.FirstName.lower() + " " + data.MiddleName.lower() + " " + data.Surname.lower()
        threshold = 30 

        def fuzzy_match(row):
            full_name = row['FULL_NAME'].lower() if row['FULL_NAME'] else ""
            return fuzz.ratio(full_name, full_name_input) >= threshold


        available_columns = df.columns.tolist()

        requested_columns = ["GIVEN_NAME_1", "GIVEN_NAME_2","GIVEN_NAME_3","SURNAME","DOB_YYYYMMDD","DOB_YYYYMMDD_DATE","AD1","SUB_DISTRICT","DISTRICT","CITY","REGENCY","PROVINCE","POSTCODE","MOBILE","EMAIL"]
        
        if requested_columns:
            valid_columns = [col for col in requested_columns if col in available_columns]
        else:
            valid_columns = available_columns  
        
        df = df[df.apply(fuzzy_match, axis=1)]


        df['match_score'] = (
            df['FULL_NAME'].apply(lambda x: max(fuzz.token_set_ratio(x.lower() if x else "", data.FirstName.lower()), textdistance.jaro_winkler(x.lower() if x else "", data.FirstName.lower()) * 100)) +\
            df['FULL_NAME'].apply(lambda x: max(fuzz.token_set_ratio(x.lower() if x else "", data.MiddleName.lower()), textdistance.jaro_winkler(x.lower() if x else "", data.MiddleName.lower()) * 100)) +\
            df['FULL_NAME'].apply(lambda x: max(fuzz.token_set_ratio(x.lower() if x else "", data.Surname.lower()), textdistance.jaro_winkler(x.lower() if x else "", data.Surname.lower()) * 100)) +\
            df['DOB_YYYYMMDD_DATE'].apply(lambda x: 75 if x and data.Dob and x == date.fromisoformat(data.Dob) else 0) +\
            df['FULL_ADDRESS'].apply(lambda x: max(fuzz.token_set_ratio(x.lower() if x else "", data.AddressElement1.lower()), textdistance.jaro_winkler(x.lower() if x else "", data.AddressElement1.lower()) * 100)) +\
            df['FULL_ADDRESS'].apply(lambda x: max(fuzz.token_set_ratio(x.lower() if x else "", data.AddressElement2.lower()), textdistance.jaro_winkler(x.lower() if x else "", data.AddressElement2.lower()) * 100)) +\
            df['FULL_ADDRESS'].apply(lambda x: max(fuzz.token_set_ratio(x.lower() if x else "", data.AddressElement3.lower()), textdistance.jaro_winkler(x.lower() if x else "", data.AddressElement3.lower()) * 100)) +\
            df['FULL_ADDRESS'].apply(lambda x: max(fuzz.token_set_ratio(x.lower() if x else "", data.AddressElement4.lower()), textdistance.jaro_winkler(x.lower() if x else "", data.AddressElement4.lower()) * 100))
        )
        
        df_sorted = df.sort_values(by='match_score', ascending=False).reset_index(drop=True)
        df = df.sort_values(by='match_score', ascending=False).head(1)
    
        # df['Dob'] = pd.to_datetime(df['DOB_YYYYMMDD_DATE'].str.split('.').str[0], format='%Y%m%d').dt.date
        df['Dob'] = pd.to_datetime(df['DOB_YYYYMMDD_DATE'], format='%Y-%m-%d', errors='coerce').dt.date
        # return df.to_dict(orient='records')
        # return df['DOB_YYYYMMDD_DATE'].values[0]

        df = df.fillna("").replace('<NA>','').reset_index(drop=True)
        fields = [
        ('GIVEN_NAME_1', data.FirstName, 0),
        ('GIVEN_NAME_2', data.MiddleName.split()[0] if data.MiddleName else "", 1),
        ('SURNAME', data.Surname, 3)
            ]
        if data.MiddleName and len(data.MiddleName.split()) > 1:
            fields.append(('GIVEN_NAME_3', data.MiddleName.split()[1], 2))
        def update_name_str(row):
            name_Str = "XXXX" 
            for db_column, input_field, str_index in fields:
                name_Str = apply_name_matching(row, name_Str, db_column, input_field, str_index)
            return name_Str
        df['Name Match Str'] = df.apply(update_name_str, axis=1)
        df['First Name Similarity'] = df.apply(lambda row: max(textdistance.jaro_winkler(row['FULL_NAME'].lower(), data.FirstName.lower()) * 100, fuzz.partial_token_sort_ratio(row['FULL_NAME'].lower(), data.FirstName.lower())), axis=1).astype(int)
        df['Middle Name Similarity'] = df.apply(lambda row: max(textdistance.jaro_winkler(row['FULL_NAME'].lower(), data.MiddleName.lower()) * 100, fuzz.partial_token_sort_ratio(row['FULL_NAME'].lower(), data.MiddleName.lower())), axis=1).astype(int)
        df['Surname Similarity'] = df.apply(lambda row: max(textdistance.jaro_winkler(row['FULL_NAME'].lower(), data.Surname.lower()) * 100, fuzz.partial_token_sort_ratio(row['FULL_NAME'].lower(), data.Surname.lower())), axis=1).astype(int)


        if df['Name Match Str'][0][0] == 'T':
            df['Given Name 1 Similarity'] = 100
        if df['Name Match Str'][0][1] == 'T':
            df['Given Name 2 Similarity'] = 100
        if df['Name Match Str'][0][2] == 'T':
            df['SurName Similarity'] = 100

        full_name_request = (data.FirstName.strip() + " " + data.MiddleName.strip() + " "+ data.Surname.strip()).strip().lower()
        full_name_matched = (df['FULL_NAME'][0].strip()).lower()
        name_obj = Name(full_name_request)
        match_results = {
            "Exact Match": ((df['Name Match Str'] == 'EEEE') |(df['Name Match Str'] == 'EEXE') ).any(),
            "Hyphenated Match": name_obj.hyphenated(full_name_matched),
            "Transposed Match": name_obj.transposed(full_name_matched),
            "Middle Name Mismatch": df['Name Match Str'][0].startswith('E') and df['Name Match Str'][0].endswith('E'),
            "Initial Match": name_obj.initial(full_name_matched),
            "SurName only Match": df['Name Match Str'].str.contains('^[ETMD].*E$', regex=True).any(),
            "Fuzzy Match": name_obj.fuzzy(full_name_matched),
            "Nickname Match": name_obj.nickname(full_name_matched),
            "Missing Part Match": name_obj.missing(full_name_matched),
            "Different Name": name_obj.different(full_name_matched)
        }
        match_results = {k: v for k, v in match_results.items() if v}
        top_match = next(iter(match_results.items()), ("No Match Found", ""))

        df['NameMatchLevel'] = top_match[0]

        df['full_name_similarity'] = df.apply(lambda row: max(textdistance.jaro_winkler(row['FULL_NAME'].lower(), full_name_input.lower()) * 100, fuzz.partial_token_sort_ratio(row['FULL_NAME'].lower(), full_name_input.lower())), axis=1)
        df['full_name_similarity'] = df['full_name_similarity'].apply(lambda score: int(score) if score > 65 else 0)
        if fuzz.token_sort_ratio(full_name_request,full_name_matched)==100 and top_match[0] !='Exact Match':
            df['full_name_similarity'] = 100

        if 'Dob' in df.columns:
            df['dob_match'] = True if df['Dob'].apply(lambda x: Dob(data.Dob).exact(x))[0]=='Exact Match' else False
        if 'MOBILE' in df.columns:
            df['MobileMatch'] = True if str(int(df['MOBILE'][0])) == data.Mobile else False
        if 'EMAIL' in df.columns:
            df['EmailMatch'] = True if df['EMAIL'][0] == data.Email else False
        

        if data.CountryPrefix in ('indonisia','mx','uae','saudi'):
            df['addressElement1_similarity'] = df[['FULL_ADDRESS', 'AD1']].apply(lambda x: max(fuzz.token_set_ratio(x[0].lower(), data.AddressElement1.lower()), fuzz.partial_token_sort_ratio(x[1].lower(), data.AddressElement1.lower())), axis=1).apply(lambda score: int(score) if score > 65 else 0) 
            weight1 = 50 if 85<=df['addressElement1_similarity'][0] <=100 else 30 if 70<=df['addressElement1_similarity'][0] <85 else 0 
            
            df['addressElement2_similarity'] = df[['FULL_ADDRESS', 'SUB_DISTRICT']].apply(lambda x: max(fuzz.token_set_ratio(x[0].lower(), data.AddressElement2.lower()), fuzz.partial_token_sort_ratio(x[1].lower(), data.AddressElement2.lower())), axis=1).apply(lambda score: int(score) if score > 65 else 0) 
            weight2 = 20 if 85<=df['addressElement2_similarity'][0] <=100 else 25 if 70<=df['addressElement2_similarity'][0] <85 else 0 
            
            df['addressElement3_similarity'] = df[['FULL_ADDRESS', 'REGENCY']].apply(lambda x: max(fuzz.token_set_ratio(x[0].lower(), data.AddressElement3.lower()), fuzz.partial_token_sort_ratio(x[1].lower(), data.AddressElement3.lower())), axis=1).apply(lambda score: int(score) if score > 65 else 0)  
            weight3 = 10 if 85<=df['addressElement3_similarity'][0] <=100 else  0

            df['addressElement4_similarity'] = df[['FULL_ADDRESS', 'PROVINCE']].apply(lambda x: max(fuzz.token_set_ratio(x[0].lower(), data.AddressElement4.lower()), fuzz.partial_token_sort_ratio(x[1].lower(), data.AddressElement4.lower())), axis=1).apply(lambda score: int(score) if score > 65 else 0)
            weight4 = 20 if 85<=df['addressElement4_similarity'][0] <=100 else 0 
            

            total_weight = weight1+weight2+weight3+weight4

        else:
            total_weight = textdistance.jaro_winkler(df['ADDRESS'][0].lower().strip(), data.address_line1.lower().strip()) * 100
            df['address_line_similarity'] = total_weight



        if total_weight > 90:
            match_level = "Full Match"
            Full_Address_Score = total_weight

        elif 70 <= total_weight <= 90:
            match_level = 'Partial Match'
            Full_Address_Score = total_weight
        

        else:
            match_level = 'No Match'
            Full_Address_Score = total_weight

        df['AddressMatchLevel'] = match_level
        df['FullAddressScore'] = Full_Address_Score
        matching_levels = get_matching_level(df,data.Dob,data.Mobile,data.Email,df['full_name_similarity'][0],total_weight)
        df['Overall Matching Level'] = ', '.join(matching_levels)
        matching_levels1 = get_mobile_email_matching_level(df,data.Dob,data.Mobile,data.Email,df['full_name_similarity'][0],total_weight)
        df['Overall Matching Level1'] = ', '.join(matching_levels1)

        df["Overall Verified Level"] = append_based_on_verification(df,verified_by=True)
        df["Overall Contact Verified Level"] = append_mobile_email_verification(df,verified_by=True)

        if (df['Overall Verified Level'][0]  != 'No Match' ):
            df['IDVRecordVerified'] = True
            df['IDVMultiLevelVerification'] = False
            

        else:
            

            df['IDVRecordVerified'] = False
            df['IDVMultiLevelVerification'] = False



        df_transposed = df.T
        df_transposed.columns = ['Results']

 
        index_col = ['Overall Verified Level','Overall Contact Verified Level','IDVRecordVerified','IDVMultiLevelVerification']
        
        df_transposed_new = df_transposed.loc[index_col].rename({"Overall Verified Level":"IDVVerifiedLevel","Overall Contact Verified Level":"IDVContactVerifiedLevel"})
        IDV_Verified_Level = {
            "M1": "Full Name Full Address DOBMatch",
            "N1": "Full Name Full Address Match",
            "M2": "Full Name DOBMatch",
            "P1": "Full Name, Mobile, and Email",
            "P2": "Full Name and Mobile",
            "P3": "Full Name and Email"}
        
        MultiSourceLevel = {
            True: "Verified by two or more independent sources",
            False: "Failed MultiSources verification"
        }
        SingleSourceLevel = {
            True: "A Verified Record with multiple attributes",
            False: "Non Verified Record"}
        ID_Level ={
            True: "ID Number Verified",
            False: "ID Number Not Verified"
        }

        df_transposed_new['Description'] = df_transposed_new['Results'].apply(lambda x: IDV_Verified_Level.get(x, ''))
        

        end_time = time.time()

        if data.IDNumber:

            if df_transposed.loc['ID_CARD','Results']==data.IDNumber:
                df_transposed_new.loc['NIKVerified', 'Results'] = True
            else :
                df_transposed_new.loc['NIKVerified', 'Results'] = False
        #     # st.write("df_transposed.loc['ID_CARD']", df_transposed.loc['ID_CARD','Results'])
            df_transposed_new.loc['NIKVerified', 'Description'] = ID_Level.get(df_transposed_new.loc['NIKVerified', 'Results'], '')
     
        df_transposed_new.loc['IDVRecordVerified', 'Description'] = SingleSourceLevel.get(df_transposed_new.loc['IDVRecordVerified', 'Results'], '')
        df_transposed_new.loc['IDVMultiLevelVerification', 'Description'] = MultiSourceLevel.get(df_transposed_new.loc['IDVMultiLevelVerification', 'Results'], '')
        
        if data.IDNumber:
            df_transposed_new = df_transposed_new.reindex(index=['NIKVerified','IDVRecordVerified','IDVVerifiedLevel', 'IDVContactVerifiedLevel',  'IDVMultiLevelVerification'])
        else:
            df_transposed_new = df_transposed_new.reindex(index=['IDVRecordVerified','IDVVerifiedLevel', 'IDVContactVerifiedLevel',  'IDVMultiLevelVerification'])

        

        if data.CountryPrefix in ('au','nz'):
            df_transposed.loc['POSTCODE', 'Results'] = str(int(df_transposed.loc['POSTCODE', 'Results']))

        if data.CountryPrefix in ('au','nz'):
            system_returned_df = df_transposed.loc[["FIRSTNAME","MIDDLENAME","LASTNAME","Dob","ADDRESS","SUBURB",
                                                "STATE","POSTCODE","MOBILE","EMAIL"]]
        else:
            # system_returned_df = df_transposed.loc[["FIRSTNAME","MIDDLENAME","LASTNAME","Dob","ADDRESS","MOBILE","EMAIL"]]    
            system_returned_df = df_transposed.loc[valid_columns+['FULL_ADDRESS']]
            system_returned_df.loc['MiddleName'] = system_returned_df.loc['GIVEN_NAME_2'].fillna('') + ' ' + system_returned_df.loc['GIVEN_NAME_3'].fillna('') 

            if 'DOB_YYYYMMDD' in system_returned_df.index and 'GIVEN_NAME_2' in system_returned_df.index and 'GIVEN_NAME_3' in system_returned_df.index:
                system_returned_df = system_returned_df.drop(['DOB_YYYYMMDD','GIVEN_NAME_2','GIVEN_NAME_3'])
            if 'Dob' not in system_returned_df.index:
                system_returned_df.loc['Dob'] = df_transposed.loc['Dob']

 
            system_returned_df.rename(index={
                'GIVEN_NAME_1': 'FirstName',
                'SURNAME': 'Surname'
            }, inplace=True)
            index_order = ['FirstName', 'MiddleName', 'Surname', 'FULL_ADDRESS','AD1', 'SUB_DISTRICT', "DISTRICT","CITY","REGENCY","PROVINCE","POSTCODE","MOBILE","EMAIL", 'Dob']

            # ------------------------------------------------------------------------------
            system_returned_df = system_returned_df.reindex(index=index_order)
            system_returned_df.loc['FULL_ADDRESS'] = system_returned_df.loc['FULL_ADDRESS'].str.strip()
            system_returned_df = system_returned_df.loc[['FULL_ADDRESS']].rename(index={'FULL_ADDRESS':'Address'})

        
        if data.CountryPrefix in ('au','nz'):
            similarity_returned_df = df_transposed.loc[["Given Name 1 Similarity","Given Name 2 Similarity","SurName Similarity",
                "full_name_similarity","NameMatchLevel","dob_match","address_line_similarity",
                "suburb_similarity","state_similarity","postcde_similarity","AddressMatchLevel","FullAddressScore"]]
            col_order = ["NameMatchLevel", "FullNameScore", "Given Name 1 Score", "Given Name 2 Score",
                    "SurnameScore", "AddressMatchLevel", "FullAddressScore","Address Line Score",
                    "Suburb Score","State Score", "Postcde Score","DOBMatch"]
        if data.CountryPrefix in ('indonisia','mx','uae','saudi'):
            similarity_returned_df = df_transposed.loc[["First Name Similarity","Middle Name Similarity","Surname Similarity",
                "full_name_similarity","NameMatchLevel","dob_match","addressElement1_similarity",
                "addressElement2_similarity","addressElement3_similarity","addressElement4_similarity","AddressMatchLevel","FullAddressScore","MobileMatch","EmailMatch"]]
            col_order = ["SourceStatus","ErrorMessage","NameMatchLevel", "FullNameScore", "FirstNameScore", "MiddleNameScore",
                    "SurnameScore", "AddressMatchLevel", "FullAddressScore","AddressElement1Score",
                    "AddressElement2Score","AddressElement3Score","AddressElement4Score","DOBMatch","MobileMatch","EmailMatch"]
        else:
            similarity_returned_df = df_transposed.loc[["Given Name 1 Similarity","Given Name 2 Similarity","SurName Similarity",
                "full_name_similarity","NameMatchLevel","dob_match","address_line_similarity",
                "AddressMatchLevel","FullAddressScore"]]
            col_order = ["SourceStatus","ErrorMessage","NameMatchLevel", "FullNameScore", "Given Name 1 Score", "Given Name 2 Score",
                    "SurnameScore", "AddressMatchLevel", "FullAddressScore","Address Line Score",
                    "DOBMatch"]

        # st.markdown(':green[**Scoring**]')
        if data.CountryPrefix not in ('indonisia','mx','uae','saudi'):
            similarity_returned_df.rename({"Given Name 1 Similarity":"Given Name 1 Score", "Given Name 2 Similarity":"Given Name 2 Score",
                                    "SurName Similarity":"SurnameScore","full_name_similarity":"FullNameScore",
                                    "dob_match":"DOBMatch","address_line_similarity":"Address Line Score","suburb_similarity":"Suburb Score",
                                    "state_similarity":"State Score","postcde_similarity":"Postcde Score"},inplace=True)
        
        else:
            similarity_returned_df.rename({"First Name Similarity":"FirstNameScore", "Middle Name Similarity":"MiddleNameScore",
                                    "Surname Similarity":"SurnameScore","full_name_similarity":"FullNameScore",
                                    "dob_match":"DOBMatch","addressElement1_similarity":"AddressElement1Score",
                                    "addressElement2_similarity":"AddressElement2Score","addressElement3_similarity":"AddressElement3Score",
                                    "addressElement4_similarity":"AddressElement4Score"},inplace=True)
 
            similarity_returned_df.loc['SourceStatus', 'Results'] = "Successful"
            similarity_returned_df.loc['ErrorMessage','Results'] = ""
            similarity_returned_df = similarity_returned_df.reindex(col_order) 

        execution_time = time.time() - start_time
        print(f"Execution time: {execution_time} seconds")

        # Description = { 
        #     "IDVVerifiedLevel" : {
        #         "M1": "Full Name Full Address DOBMatch",
        #         "N1": "Full Name Full Address Match",
        #         "M2": "Full Name DOBMatch",
        #         "P1": "Full Name, Mobile, and Email",
        #         "P2": "Full Name and Mobile",
        #         "P3": "Full Name and Email"},
        #     "MultiSourceLevel": {
        #         True: "M1>=2 or (M1>=1 and M2>=1) or (M1>=1 and N1>=1) or (M2>=1 and N1>=1)",
        #         False: "otherwise"},
        #     "NameMatchLevels": {
        #         "Exact Match": "Full Name Match", 
        #         "Hyphenated Match": "Hyphenated Match",
        #         "Transposed Match": "Transposed Match",
        #         "Middle Name Mismatch": "Middle Name Mismatch",
        #         "Initial Match": "Initial Match",
        #         "SurName only Match": "SurName only Match"
        #     },
        # }
        
        return {
            "Time": execution_time,
            **df_transposed_new[['Results']].rename(columns={'Results':'Summary'}).to_dict(),
            **system_returned_df[['Results']].rename(columns={'Results':'ReturnItems'}).to_dict(),
            **similarity_returned_df.rename(columns={'Results':'Scoring'}).to_dict()
            # "Description":Description
        }
        
    

 
        
    # except snowflake.connector.errors.ProgrammingError as e:
    #     raise HTTPException(status_code=500, detail=f"Error executing query: {e}")

    finally:
        pass


@app.get("/")
async def read_root(credentials: HTTPBasicCredentials = Depends(security)):
    user = verify_credentials(credentials)
    return {"message": "Welcome to the User Verification API"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)