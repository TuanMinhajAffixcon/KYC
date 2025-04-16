import textdistance
import re
import streamlit as st
import pandas as pd
from datetime import datetime

def build_match_conditions(name, column_name, reference_column):
    if name:
        return f"""
            CASE
                WHEN '{name}' != '' AND 
                    {' OR '.join([f"{reference_column} LIKE '%' || '{part}' || '%'" for part in name.split()])}
                THEN 1.0
                ELSE 0
            END
        """
    return '0'

# def build_match_conditions(name, column_name, reference_column):
#     if name:
#         return f"""
#             CASE
#                 WHEN '{name}' != '' AND 
#                     {' OR '.join([f"{reference_column} LIKE '%' || '{part}' || '%'" for part in name.split()])}
#                 THEN 1.0
#                 WHEN '{name}' != '' AND 
#                     {' OR '.join([f"SOUNDEX({column_name}) = SOUNDEX('{part}')" for part in name.split()])}
#                 THEN 0.8
#                 ELSE 0
#             END
#         """
#     return '0'
#-----------------------------------------Name Components -------------------------------------------------------------=
name_match_actions = {
    'exact': 'E',
    'nickname': 'N',
    'hyphenated': 'H',
    'fuzzy': 'F',
    'initial': 'I',
    'transposed': 'T',
    'missing': 'M',
    'different': 'D'
}


class Name:
    def __init__(self, name):
        self.name = name.lower()  # Convert to lowercase
    
    def exact(self, other_name):
        """
        Checks if the current name exactly matches the other name.
        Both names must be more than one character long.
        """
        other_name = other_name.lower()  # Convert to lowercase

        if len(self.name) > 1 and len(other_name) > 1 and self.name == other_name:
            return 'Exact Match'
        return False
    
    def hyphenated(self, other_name):
        """
        Checks if the current name matches a hyphenated version of the other name.
        Example: 'Smith' matches 'Smith-Jones'
        """
        other_name = other_name.lower()  # Convert to lowercase
        if '-' in other_name and self.name in other_name.split('-'):
            return "Hyphenated Name"
        return False

    def fuzzy(self, other_name, threshold=0.85):
        """
        Checks if the current name matches the other name based on fuzzy matching.
        The threshold determines the minimum similarity score required to consider it a match.
        Example: 'Brown' matches 'Browne'
        """
        other_name = other_name.lower()  # Convert to lowercase
        # similarity = fuzz.ratio(self.name, other_name)
        similarity = textdistance.jaro_winkler(self.name, other_name)
        if similarity >= threshold:
            return f"Fuzzy Match with similarity score: {similarity}"
        return False

    def nickname(self, other_name):
        """
        Checks if the current name matches a nickname or an alternative spelling of the other name.
        Example: 'Bob' matches 'Robert'
        """
        other_name = other_name.lower()  # Convert to lowercase
        nicknames_database = {
            "bob": ["robert"],
            "roberto": ["robert"],
            "enrique": ["henry", "hank"],
            "john": ["j"]
            # Add more nicknames and variations here
        }
        
        # Look up nicknames in the database
        if self.name in nicknames_database:
            if other_name in nicknames_database[self.name]:
                return "Nickname Match"
        return False

    def initial(self, other_name):
        """
        Checks if the current name is an initial of the other name or vice versa.
        Example: 'John' matches 'J'
        """
        other_name = other_name.lower()  # Convert to lowercase
        # if len(self.name) == 1 and other_name.startswith(self.name):
        if other_name.startswith(self.name[0]):
            return "Initial Match"
        if len(other_name) == 1 and self.name.startswith(other_name):
            return "Initial Match"
        return False

    def transposed(self, other_name):
        """
        Checks if the components of the names are transposed.
        Example: 'John Robert Smith' matches 'Robert John Smith'
        """
        self_parts = self.name.split()
        other_name = other_name.lower()  # Convert to lowercase
        other_parts = other_name.split()
        
        if len(self_parts) == len(other_parts) and sorted(self_parts) == sorted(other_parts):
            return "Transposed Match"
        return False

    def missing(self, other_name):
        """
        Checks if the current name is a subset of the other name or vice versa.
        Example: 'John Robert Smith' matches 'John Smith'
        """
        other_name = other_name.lower()  # Convert to lowercase
        if self.name in other_name or other_name in self.name:
            return "Missing Part Match"
        return False

    def different(self, other_name):
        """
        Checks if there is no match between the names.
        Example: 'John' matches 'Robert'
        """
        other_name = other_name.lower()  # Convert to lowercase
        if self.name != other_name:
            return "Different Name"
        return False
    
def apply_name_matching(row, name_Str, db_column, input_field, str_index):
    name_obj = Name(input_field)  # Initialize Name object with the input_field

    # Iterate through all match types
    for match_type, replacement_char in name_match_actions.items():
        # Dynamically call the corresponding method (exact, nickname, etc.)
        if getattr(name_obj, match_type)(row[db_column]):
            # Replace the character at str_index in name_Str with the replacement_char
            name_Str = name_Str[:str_index] + replacement_char + name_Str[str_index+1:]
            break  # Stop after the first match is found

    return name_Str

#---------------------------------------------------------------------------------------------------------------------=


#-----------------------------------------DOB Components -------------------------------------------------------------=
class Dob:
    def __init__(self, dob):
        self.dob = dob  # Initialize with dob
    
    def exact(self, other_dob):
        """
        Checks if the current dob exactly matches the other dob.
        """
        # Convert both dobs to strings for comparison
        if str(self.dob) == str(other_dob):
            return 'Exact Match'
        return 'No Match'
    
#---------------------------------------------------------------------------------------------------------------------=

#-----------------------------------------Address Components -------------------------------------------------------------=
class Address:
    def __init__(self, parsed_address,source_address):
        self.parsed_address = parsed_address
        self.source_address = source_address

    def address_id_match(self, address_str):
        """
        D= AddressID
        An exact match based on the GNAF AddressID. When this match is made,
        all other characters of the match string are set to 'X'.
        """
        if self.parsed_address['Gnaf_Pid'] == self.source_address.get('Gnaf_Pid'):
            return address_str[:0] + "D" + address_str[1:]
        return address_str
    
    def address_line1_match(self, address_str):
        """
        A=Address Line 1
        An exact match based on Address Line 1. When this match is made,
        the match characters for Unit Number, Street Number & Street name
        are set to 'X'.
        """

        # Check if the address line matches exactly
        if self.parsed_address["Ad1"].lower() == self.source_address['Ad1'].lower():
            address_str = address_str[:0] + "A" + address_str[1:]

        
        else:
            ###unit No
            if self.exact_match('unit_no'):
                address_str = address_str[:1] + "E" + address_str[2:]  
            elif self.missing_unit_number():
                address_str = address_str[:1] + "M" + address_str[2:]  
            elif self.different('unit_no'):
                address_str = address_str[:1] + "Z" + address_str[2:]  

            ###Street No
            if self.exact_match('street_no'):
                address_str = address_str[:2] + "E" + address_str[3:]  
            elif self.street_number_range_match():
                address_str = address_str[:2] + "R" + address_str[3:]  
            elif self.different('street_no'):
                address_str = address_str[:2] + "Z" + address_str[3:]  

            ###Street Name
            if self.exact_match('street_name'):
                address_str = address_str[:3] + "E" + address_str[4:]
            elif self.partial_street_name_match():
                address_str = address_str[:3] + "F" + address_str[4:]   
            elif self.different('street_name'):
                address_str = address_str[:3] + "Z" + address_str[4:]  

        ###Postcode and Locality
        if self.both_locality_postcode_match():
            address_str = address_str[:4] + "B" + address_str[5:]  
        elif self.locality_match():
            address_str = address_str[:4] + "L" + address_str[5:]  
        elif self.postcode_match():
            address_str = address_str[:4] + "P" + address_str[5:] 
        elif self.different("Suburb"):
            address_str = address_str[:4] + "Z" + address_str[5:] 
        elif self.different("Postcode"):
            address_str = address_str[:4] + "Z" + address_str[5:] 

        ##State
        if self.exact_match('State'):
            address_str = address_str[:-1] + "E" + address_str[6:]  

        elif self.different('State'):
                address_str = address_str[:5] + "Z" + address_str[6:]  

        # Return the original address_str if no match and no regex match
        return address_str
    
    def address_split(self):
        # Regex pattern to capture Unit No, Street No, Street Name, Street Type
        pattern = r'(?:(Unit\s\d+)\s)?(\d+)\s([A-Za-z\s]+)\s(\w+)$'
        
        match = re.match(pattern, self.source_address.strip())
        if match:
            unit_no = match.group(1) if match.group(1) else ''
            street_no = match.group(2)
            street_name = match.group(3).strip()
            street_type = match.group(4)
            return {"unit_no":unit_no, "street_no":street_no, "street_name":street_name, "street_type":street_type}
        else:
            return ['', '', '', '']

    def exact_match(self, component):
        """
        E=Exact
        An exact match on the address component.
        """
        if ((self.parsed_address.get(component) !="" and self.source_address.get(component)!="") and
            (self.parsed_address.get(component).lower() == self.source_address.get(component).lower() )):
            return 'E'
        return False
    
    def missing_unit_number(self):
        # self.source_address = self.source_address.lower()

        """
        M=Missing Unit Number
        An address match where the unit number is missing in either the parsed
        or source address, but not both.
        """
        if ((((self.parsed_address.get('unit_no')  and self.source_address.get('unit_no')) and
            (self.parsed_address.get('unit_no') != self.source_address.get('unit_no'))) and
            (any(component in self.source_address.get('unit_no').split() for component in self.parsed_address.get('unit_no').split())))\
            or
            any(component in self.source_address.get('unit_no').split() for component in self.parsed_address.get('unit_no').split())):
            return 'M'
        return None

    def street_number_range_match(self):

        """
        R=Street Number Range
        A match where the street number is within plus or minus six numbers.
        """
        if (self.parsed_address['street_no'] !="" and self.source_address.get('street_no')!="")and abs(int(self.parsed_address['street_no']) - int(self.source_address.get('street_no', 0))) <= 6:
            return 'R'
        return None

    def partial_street_name_match(self):

        """
        F=Partial Street Name
        A match where the street name matches but the street type does not.
        """
        if self.parsed_address['street_name'].lower() == self.source_address.get('street_name').lower() and \
           self.parsed_address.get('street_type').lower() != self.source_address.get('street_type').lower():
            return 'F'
        return None

    def both_locality_postcode_match(self):

        """
        B=Both Locality & Postcode
        A match where both Locality/Suburb name and Postcode match.
        """
        if self.parsed_address['Suburb'].lower() == self.source_address.get('Suburb').lower() and \
           self.parsed_address['Postcode'].lower() == self.source_address.get('Postcode').lower():
            return 'B'
        return None

    def locality_match(self):
    

        """
        L=Locality
        A match where the Locality/Suburb name matches, but the Postcode is different.
        """
        if self.parsed_address['Suburb'].lower() == self.source_address.get('Suburb').lower() and \
           self.parsed_address['Postcode'] != self.source_address.get('Postcode'):
            return 'L'
        return None

    def postcode_match(self):

        """
        P=Postcode
        A match where the Postcode matches but the Locality/Suburb name is different.
        """
        if self.parsed_address['Postcode'].lower() == self.source_address.get('Postcode').lower() and \
           self.parsed_address['Suburb'] != self.source_address.get('Suburb'):
            return 'P'
        return None

    def missing_component(self):

        """
        X=Missing
        One or both of the components of the parsed input address and data source address is missing.
        """
        missing = False
        for key in self.parsed_address:
            if not self.parsed_address[key] or not self.source_address.get(key):
                missing = True
                break
        if missing:
            return 'X'
        return None

    def different(self, component):

        """
        Z=Different
        This code represents a non-match of the particular component of the address.
        """
        # if self.parsed_address.get(component) and self.source_address.get(component and \
        # self.parsed_address.get(component) !=  self.source_address.get(component)) :
        if ((self.parsed_address.get(component)  and self.source_address.get(component)) and
            (self.parsed_address.get(component) != self.source_address.get(component))):
            return 'Z'
        return False

address_match_actions = {
    'address_id_match': 'D',            # GNAF AddressID match
    'address_line1_match': 'A',         # Address Line 1 match
    'exact_match': 'E',                 # Exact match on any address component
    'missing_unit_number': 'M',         # Missing Unit Number match
    'street_number_range_match': 'R',   # Street Number Range match
    'partial_street_name_match': 'F',   # Partial Street Name match
    'both_locality_postcode_match': 'B',# Both Locality and Postcode match
    'locality_match': 'L',              # Locality/Suburb name match
    'postcode_match': 'P',              # Postcode match
    'missing_component': 'X',           # Missing component
    'different': 'Z'                    # Non-match (Different component)
}

# def address_parsing(ad1):
#     # Pattern to match when the address has a unit number (with or without prefix)
#     pattern1 = r'(?i)(?:(Unit\s\d+|unit\s\d+)|(\d+))?\s*(\d+)\s+([A-Za-z\s]+?)\s+(\w+)$'
#     # Pattern to match when the address has only three components (no unit number)
#     pattern2 = r'(?i)(\d+)\s+([A-Za-z\s]+?)\s+(\w+)$'

#     # Clean up extra spaces and match the appropriate pattern
#     cleaned_address = re.sub(r'\s+', ' ', ad1.strip())
    
#     if len(cleaned_address.split()) == 3:
#         st.write(cleaned_address)

#         source_match = re.match(pattern2, cleaned_address)
#         unit_no = ''  # No unit number in this case
#         street_no = source_match.group(1)
#         street_name = source_match.group(2).strip()
#         street_type = source_match.group(3)
#     elif len(cleaned_address.split()) == 5:
#         source_match = re.match(pattern1, cleaned_address)

#         if source_match.group(1):
#             unit_no = source_match.group(1)
#         elif source_match.group(2):
#             unit_no = source_match.group(2)
#         else:
#             unit_no = ''
#         street_no = source_match.group(3)
#         street_name = source_match.group(4).strip()
#         street_type = source_match.group(5)
#     else:
#         source_output = {
#             "unit_no": "",
#             "street_no": "",
#             "street_name": "",
#             "street_type": ""
#         }
#         return source_output
    
#     if source_match:

#         source_output = {
#             "unit_no": unit_no.strip(),
#             "street_no": street_no,
#             "street_name": street_name,
#             "street_type": street_type
#         }
#         return (source_output)

def address_parsing(ad1):
    # Pattern to match an address with an optional unit number, street number, street name, and street type
    # The street type can be any common street type (St, Rd, Ave, etc.) and is optional
    pattern = r'(?i)(unit\s*\d+)?\s*(\d+)?\s*([A-Za-z\s]+?)\s*(St|Street|Rd|Road|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Ct|Court|Way|Ln|Lane|Pl|Place|Terrace|Circle|Pkwy|Parkway|Square)?$'
    
    # Clean up extra spaces and match the appropriate pattern
    cleaned_address = re.sub(r'\s+', ' ', ad1.strip())

    # Match the cleaned address to the pattern
    source_match = re.match(pattern, cleaned_address)

    if source_match:
        # Extract the matched groups from the pattern
        unit_no = source_match.group(1) if source_match.group(1) else ''  # Optional unit number
        street_no = source_match.group(2) if source_match.group(2) else ''  # Optional street number
        street_name = source_match.group(3).strip() if source_match.group(3) else ''  # Street name
        street_type = source_match.group(4) if source_match.group(4) else ''  # Optional street type

        # Build the output dictionary
        source_output = {
            "unit_no": unit_no.strip(),
            "street_no": street_no,
            "street_name": street_name,
            "street_type": street_type
        }
        return source_output
    else:
        # If no match is found, return empty fields
        source_output = {
            "unit_no": "",
            "street_no": "",
            "street_name": "",
            "street_type": ""
        }
        return source_output
#---------------------------------------------------------------------------------------------------------------------=
def get_mobile_email_matching_level(df,dob,mobile,email,name_matching_score,address_matching_weights):

    levels = []
    # Define the score ranges and their corresponding levels
    name_score_levels = {
        (97, 100): 'FullName',
        (75, 97): 'PartialName',
    }

    # Check name matching level
    for score_range, level in name_score_levels.items():
        if score_range[0] <= name_matching_score <= score_range[1]:
            levels.append(f'{level} - {int(name_matching_score)}'+"%")

    # if 'Phone2_Mobile' in df.columns and pd.notna(df['Phone2_Mobile'].iloc[0]) and mobile !='' and str(df['Phone2_Mobile'].iloc[0]) == (mobile):
    #     levels.append('Mobile')
    # if (df['EMAILADDRESS'][0] is not None and (df['EMAILADDRESS'][0] in df['EMAILADDRESS'][0] and df['EMAILADDRESS'][0] != "") and df['EMAILADDRESS'][0] == email):
    #     levels.append('Email')
    # if 'MOBILE' in df.columns and pd.notna(df['MOBILE'].iloc[0]) and mobile !='' and str(int(df['MOBILE'].iloc[0])) == (mobile):
    if 'MOBILE' in df.columns and (df['MOBILE'].iloc[0] !="") and mobile !='' and str(int(df['MOBILE'].iloc[0])) == (mobile):
        levels.append('Mobile')
    if 'EMAIL' in df.columns and (df['EMAIL'][0] is not None and (df['EMAIL'][0] in df['EMAIL'][0] and df['EMAIL'][0] != "") and df['EMAIL'][0] == email):
        levels.append('Email')
    return levels


def append_mobile_email_verification(result, verified_by =False):
    # verified_by = result['Overall Matching Level1'][0]
    verified_by = result['Overall Matching Level'][0]

    name_terms = ["FullName", "PartialName"]
    mobile_term = "Mobile"
    email_term = "Email"


    name_check = any(term in verified_by for term in name_terms)
    mobile_check = mobile_term in verified_by
    email_check = email_term in verified_by

    if name_check and mobile_check and email_check:
        # indexes['Sources'][index].append('M1')
        if verified_by:
            return "P1"
    elif name_check and mobile_check:
        # indexes['Sources'][index].append('N1')
        if verified_by:
            return "P2"
    elif name_check and email_check:
        # indexes['Sources'][index].append('M2')
        if verified_by:
            return "P3"
    return "No Match"

def get_matching_level(df,dob,mobile,email,name_matching_score,address_matching_weights):

    levels = []
    # Define the score ranges and their corresponding levels
    name_score_levels = {
        (97, 100): 'FullName',
        (90, 97): 'PartialName',
    }

    address_score_levels = {
        (91, 100): 'FullAddress',
        (79, 90): 'PartialAddress',
    }

    # Check name matching level
    for score_range, level in name_score_levels.items():
        if score_range[0] <= name_matching_score <= score_range[1]:
            levels.append(f'{level} - {int(name_matching_score)}'+"%")


    # Check address matching level
    for score_range, level in address_score_levels.items():
        if score_range[0] <= address_matching_weights <= score_range[1]:
            levels.append(f'{level} - {int(address_matching_weights)}'+"%")
    if 'DOB' in df.columns and pd.notna(df.DOB.iloc[0]) and str(df.DOB.iloc[0]) == dob:
        levels.append('DOB - 100%')

    if 'MOBILE' in df.columns and pd.notna(df.MOBILE.iloc[0]) and df.MOBILE.iloc[0] == mobile:
        levels.append('Mobile - 100%')
    if ((df.EMAIL[0] in df.EMAIL[0] and df.EMAIL[0] != "") and df.EMAIL[0] == email):
        levels.append('Email - 100%')

    return levels



def append_based_on_verification(Overall_Matching_Level, verified_by =False):
    verified_by = Overall_Matching_Level['Overall Matching Level'][0]
    name_terms = ["FullName", "PartialName"]
    address_terms = ["Address", "PartialAddress"]
    dob_term = "DOB"

    name_check = any(term in verified_by for term in name_terms)
    address_check = any(term in verified_by for term in address_terms)
    dob_check = dob_term in verified_by

    if name_check and address_check and dob_check:
        # indexes['Sources'][index].append('M1')
        if verified_by:
            return "M1"
    elif name_check and address_check:
        # indexes['Sources'][index].append('N1')
        if verified_by:
            return "N1"
    elif name_check and dob_check:
        # indexes['Sources'][index].append('M2')
        if verified_by:
            return "M2"
    return "No Match"



def batch_process(df):
    def add_record(all_records, input_record):
        # all_records["ID"].append(input_record.get("SOURCE_Urn"))
        all_records["first_name"].append(input_record.get("First_Name"))

        all_records["middle_name"].append(input_record.get("Middle_Name"))
        all_records["sur_name"].append(input_record.get("Sur_Name"))
        all_records["dob"].append(input_record.get("DOB_Formatted"))
        all_records["address"].append(input_record.get("Ad1"))
        all_records["mobile"].append(input_record.get("Phone2_Mobile"))  # Assuming empty or default value
        all_records["email"].append(input_record.get("EmailAddress"))  # Assuming empty or default value

    all_records = {"first_name": [], "middle_name":[], "sur_name": [], "dob": [], "address": [], "mobile": [], "email": []}
    
    if df is not None:
        try:
            df = df.astype(str)

            json_records = df.to_dict(orient='records')
            for record in json_records:
                add_record(all_records, record)
            # st.write(all_records)

            return all_records
        except pd.errors.EmptyDataError:
            st.error("Uploaded file is empty.")
        except ValueError as e:
            st.error(f"Error processing file: {e}")
    
    return all_records


