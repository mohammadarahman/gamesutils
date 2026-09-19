

import json
from datetime import datetime
from triage_email_rewrite import *


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "triage_email_data.json")
#OUTPUT_HTML = os.path.join(SCRIPT_DIR, "triage_email_dashboard.html")
soup = None  # Global HTML element, updated per file
raw_subject_cache = None  # Cache raw subject for parsers

def convert_datetime(date_string):
    if not date_string:
        return ""
    try:
        # Try multiple formats
        formats = [
            "%A, %B %d, %Y %I:%M %p",  # Friday, September 18, 2026 7:38 PM
            "%m/%d/%Y %I:%M:%S %p",    # 06/17/2024 02:00:00 PM
            "%m/%d/%Y %H:%M:%S",       # 06/17/2024 14:00:00
            "%Y-%m-%d %H:%M:%S",       # 2024-06-17 14:00:00
        ]
        
        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(date_string.strip(), fmt)
                break
            except ValueError:
                continue
        
        if not dt:
            dprint(f"[WARNING] Could not parse datetime: {date_string}")
            return date_string
        
        # Format: 18SEP 19:38:00
        day_str = dt.strftime("%d")
        month_str = dt.strftime("%b").upper()
        time_str = dt.strftime("%H:%M:%S")
        formatted = f"{day_str}{month_str} {time_str}"
        dprint(f"[DEBUG] Converted: '{date_string}' -> '{formatted}'")
        return formatted
    except Exception as e:
        dprint(f"[ERROR] Error parsing date '{date_string}': {e}")
        return date_string 
    
def cleanupsubject(subject):
    """
    If subject contains ' - ' and the last part starts with
    'tsc' or 'tor', treat that last part as the server name.
    """
    if not subject:
        return subject, ""
    subject = subject.strip().lower()
    if (subject.startswith("swapping compute")):
        parts = subject.split("-")
        if len(parts) > 1:
            last_part = parts[-1].strip()
            if last_part.lower().startswith(("tsc", "tor")):
                cleaned_subject = "-".join(parts[:-1]).strip()
                return cleaned_subject, last_part
    elif (subject.startswith("alertrouter: critical")):
        subject = "alertrouter: critical"
    return subject, ""
def getdata_p(rgxstr, all=True):
    global soup
    if not soup:
        return ""
    
    results = []
    for p_tag in soup.find_all('p'):
        text = p_tag.get_text(" ", strip=True)
        match = re.search(rgxstr, text, re.IGNORECASE)
        if match:
            if match.groups():
                # If there are groups, join them with space
                item = " ".join(str(g) for g in match.groups() if g)
            else:
                # If no groups, use the whole match
                item = match.group(0)
            results.append(item)
            if not all:
                return item
    
    # Remove duplicates while preserving order
    if results:
        seen = set()
        unique_results = []
        for item in results:
            if item not in seen:
                seen.add(item)
                unique_results.append(item)
        results = unique_results
        return "<br>".join(results) if all else results[0]
    return ""
def getdata_tbl1(cols, rgxstr, red=True, compress=True):
    global soup
    if not soup:
        return ""
    
    # Find table with id="table1"
    table = soup.find('table', {'id': 'table1'})
    if not table:
        return ""
    
    results = []
    
    # Get all rows
    rows = table.find_all('tr')
    
    for row in rows:
        # If red=True, only process rows with class="colorred"
        if red:
            row_class = row.get('class', [])
            if isinstance(row_class, str):
                row_class = [row_class]
            if 'colorred' not in row_class:
                continue
        
        # Get cells in this row
        cells = row.find_all(['td', 'th'])
        
        # Skip rows where first cell is in skip list (easily extensible)
        skip_cells = ['itotools']
        skip_cnt = 0 
        if cells and cells[0].get_text(strip=True) in skip_cells:
            skip_cnt += 1
            continue
        dprint(f"[DEBUG] noSkipping row with first cell: {cells[0].get_text(strip=True)}")
        # Extract text from specified columns
        col_texts = []
        for col_idx in cols:
            if col_idx < len(cells):
                col_texts.append(cells[col_idx].get_text(strip=True))
        
        # Combine texts from columns
        combined_text = " ".join(col_texts)
        
        # Apply regex and extract all groups
        match = re.search(rgxstr, combined_text, re.IGNORECASE)
        if match:
            # Get all groups and filter out None values
            groups = [str(g) for g in match.groups() if g]
            if groups:
                # Join groups with space and add to results
                results.append(" ".join(groups))
            else:
                # If no groups, use entire match
                results.append(match.group(0))
    if skip_cnt > 0 and not results:
        return " ".join(skip_cells)
        
    print(results)
    # If compress=True, remove duplicates while preserving order
    if compress:
        seen = set()
        unique_results = []
        for item in results:
            if item not in seen:
                seen.add(item)
                unique_results.append(item)
        results = unique_results
    
    # Return results joined with space
    return " ".join(results) if results else ""
    

    
def gettabledatas(cols, headertext, red=True):
    """
    Parse table rows from HTML and return a list of columns.
    Args:
        soup (html soup) 
        cols (list[int]): zero-based column indexes to extract
        headertext (str): text that must be present in the first row of the table
        red (bool): if True, include only rows with red text
    Returns:
        list[list[str]]: list of columns, each column containing values from matching rows
    """
    global soup
    result = [[] for _ in cols]
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        # First row is the header row
        header_cells = rows[0].find_all(["td", "th"])
        header_texts = [cell.get_text(" ", strip=True) for cell in header_cells]
        # Skip table if required header text is not found in first row
        if not any(headertext.lower() in h.lower() for h in header_texts):
            continue
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            if red:
                has_red = False
                for cell in cells:
                    spans = cell.find_all("span")
                    for span in spans:
                        style = span.get("style", "").replace(" ", "").lower()
                        if "color:red" in style:
                            has_red = True
                            break
                    if has_red:
                        break
                if not has_red:
                    continue
            for idx, col in enumerate(cols):
                if col < len(cells):
                    result[idx].append(cells[col].get_text(" ", strip=True))
                else:
                    result[idx].append("")
    return result
    
def parsepath(path, segments):
    if not isinstance(path, str) or not path.strip():
        return [""] * len(segments)
    if "/" not in path and "\\" not in path:
        return [""] * len(segments)
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    return [parts[i] if isinstance(i, int) and 0 <= i < len(parts) else "" for i in segments]
# ----------------------------
# File helpers
# ----------------------------
def load_input_json(path):
    with open(path, "r", encoding="utf-16") as f:
        return json.load(f)
def load_html_file(html_path):
    if not os.path.exists(html_path):
        dprint(f"[WARN] Missing HTML file: {html_path}")
        return None
    encodings_to_try = ["utf-8", "utf-8-sig", "utf-16", "cp1252", "latin-1"]
    for enc in encodings_to_try:
        try:
            with open(html_path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    dprint(f"[WARN] Could not decode HTML file: {html_path}")
    return None
# ----------------------------
# Save / render
# ----------------------------
def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
# ----------------------------
# Parser functions (subject -> parse function registry)
# ----------------------------
def default_parse_result():
    return {
        "info1": "",
        "info2": "-",
        "path": "-",
        "users": "-",
        "notes": "",
        "rfc": "",
        "dashboard": "",
    }


def get_common_links():
    global soup
    out = {"rfc": "", "dashboard": ""}
    if not soup:
        return out
    text_lines = soup.get_text("\n", strip=True)

    match = re.search(r"RFC:\s*(https?://\S+)", text_lines, re.IGNORECASE)
    if match:
        out["rfc"] = match.group(1).strip()
    else:
        el = soup.select_one(".rfc")
        out["rfc"] = el.get_text(" ", strip=True) if el else ""

    match = re.search(r"Dashboard:\s*(https?://\S+)", text_lines, re.IGNORECASE)
    if match:
        out["dashboard"] = match.group(1).strip()
    else:
        el = soup.select_one(".dashboard")
        out["dashboard"] = el.get_text(" ", strip=True) if el else ""

    return out


def parse_base():
    return {}




def parse_ttd_ref_vol_fill():
    global soup
    text = soup.get_text(" ", strip=True)
    match = re.search(r"Summary: (\S+)\s+volume\s+on\s+(\S+)\s+is\s+(\S+)\s+full", text, re.IGNORECASE)
    if match:
        return {
            "info2": "<b>" + match.group(2) + "</b> Vol: " + match.group(1),
            "info1": match.group(3),
        }
    dprint("TTDrefVolFill parser: no match")
    return {}


def parse_critical_its():
    global soup, raw_subject_cache
    dprint(f"[PARSER] parse_critical_its")
    text = soup.get_text(" ", strip=True)
    out = {"path": "--"}
    match = re.search(
        r"Summary:\s*ITS\s*ticket\s*(\d+)\s*needs\s*your\s*attention:\s*(.+?)(?=\s+rfc:|\s+dashboard:|$)",
        text,
        re.IGNORECASE,
    )
    if match:
        out.update({
            "info1": match.group(1),
            "info2": match.group(2).strip(),
        })
    else:
        dprint("CriticalITS parser: no match")

    matches = re.findall(r"rfc:\s*(\S+)", text, re.IGNORECASE | re.MULTILINE)
    if matches:
        out["path"] = "<br> ".join(f"<a href={its}>{its}</a>" for its in matches)
    return out

def parse_critical():
    global soup, raw_subject_cache
    dprint(f"[PARSER] parse_critical")
    text = soup.get_text(" ", strip=True)
    out = {"path": "--"}
    raw_subject = raw_subject_cache

    # Shared: build Info1 label from raw subject, linked to RFC
    rfc_match = re.search(r"rfc:\s*(https?://\S+)", text, re.IGNORECASE)
    rfc_link = rfc_match.group(1).strip() if rfc_match else ""
    subj_match = re.search(r"AlertRouter: CRITICAL (.*) is firing", raw_subject, re.IGNORECASE)
    label = subj_match.group(1).strip() if subj_match else raw_subject
    if label:
        out["info1"] = f'<a href="{rfc_link}">{label}</a>' if rfc_link else label

    # Per-type: fill server (Info2) and path based on what the subject contains
    if "Emergency rampdown" in raw_subject:
        match = re.search(r"description:\s*(\S+)", text, re.IGNORECASE)
        if match:
            desc_path = match.group(1).strip()
            parts = [p for p in desc_path.replace("\\", "/").split("/") if p]
            out["info2"] = parsepath(desc_path, [1])[0]
            out["path"] = "/" + "/".join(parts[:-1]) if len(parts) > 1 else desc_path
    elif "MultipleClientsDownNetbatchClass" in raw_subject:
        # description: More than 50% of SLES12_short in pool orto_e are not available.
        matches = re.findall(r"description: More than \S+ of (\S+)\s+in pool\s+(\S+)\s+are not available", text, re.IGNORECASE)
        if matches:
            out["path"] = "<br>".join(f"{cls} - {pool}" for cls, pool in matches)
    elif "MLCWorkerNodeSwapping" in raw_subject:
        match = re.search(r"description:\s*(\S+):\s*Swap usage is above (.+)", text, re.IGNORECASE)
        if match:
            out["info2"] = match.group(1).strip()
            out["path"] = match.group(2).strip()
        else:
            match = re.search(r"description:\s*Machine\s+(\S+)\s+is\s+swapping", text, re.IGNORECASE)
            if match:
                out["info2"] = match.group(1).strip()
    #one condition for subject containing NetbatchQOS is firing
    elif "NetbatchQOS is firing" in raw_subject:
        matches = re.findall(r"Time\s+to\s+do\s+nbstatus\s+jobs\s+--target\s+(\S+)\s+is\s+high,\s+with\s+a\s+value\s+of\s+(\d+)\s+secs", text, re.IGNORECASE)
        if matches:
            out["info2"] = ", ".join(f"{target} - {value} secs" for target, value in matches)
        else:
            dprint("NBStatus parser: no match")

    return out



def parse_emergency_rampdown():
    global soup
    dprint(f"[PARSER] parse_emergency_rampdown")
    text = soup.get_text(" ", strip=True)
    out = {"info1": "", "info2": "none"}
    match = re.search(r"job_path:\s*(\S+)", text, re.IGNORECASE)
    if match:
        out["path"] = match.group(1)
    return out


def parse_ttd_netapp_aggr():
    global soup
    dprint(f"[PARSER] parse_ttd_netapp_aggr")
    text = soup.get_text(" ", strip=True)
    match = re.search(r"Summary:\s+Aggregate\s+(\S+)\s+is\s+at\s+(\S+)%", text, re.IGNORECASE)
    if match:
        return {
            "info2": match.group(1),
            "info1": match.group(2) + "%",
        }
    dprint("TTDNetAppAggr parser: no match")
    return {}


def parse_aggr_will_fill():
    global soup
    dprint(f"[PARSER] parse_aggr_will_fill")
    text = soup.get_text(" ", strip=True)
    match = re.search(r"Summary:\s+(\S+)\s+will\s+fill\s+in\s+less\s+than\s+(\d+)\s+days", text, re.IGNORECASE)
    if match:
        return {
            "info2": match.group(1),
            "info1": match.group(2) + " day",
        }
    dprint("AggrWillFill parser: no match")
    return {}


def parse_high_nb_job_wait():
    global soup
    dprint(f"[PARSER] parse_high_nb_job_wait")
    text = soup.get_text("\n", strip=True)
    out = {}

    descriptions = re.findall(
        r"description:\s*(.*?)(?=\n\s*(?:description:|rfc:|dashboard:|-{5,}|$))",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    classes = []
    pool_paths = []

    for raw_desc in descriptions:
        desc = " ".join(raw_desc.split())
        if not desc:
            continue

        class_match = re.search(r"\bclass\s+(.+?)\s+for\s+last\b", desc, re.IGNORECASE)
        pool_match = re.search(r"\bin\s+(\S+)\s+in\s+qslot\b", desc, re.IGNORECASE)
        qslot_match = re.search(r"\bin\s+qslot\s+(\S+)", desc, re.IGNORECASE)

        if class_match:
            classes.append(class_match.group(1).strip())

        pool = pool_match.group(1).strip() if pool_match else ""
        qslot = qslot_match.group(1).strip() if qslot_match else ""
        if pool or qslot:
            pool_paths.append(f"{pool} {qslot}".strip())

    if classes:
        out["info1"] = "<br>".join(dict.fromkeys(classes))
    if pool_paths:
        out["info2"] = "<br>".join(dict.fromkeys(pool_paths))

    if not out:
        dprint("HighNBJobWait parser: no description match")

    return out
    
def parse_netbatchqos():
    global soup
    dprint(f"[PARSER] parse_netbatchqos")
    text = soup.get_text(" ", strip=True)
    out = {}
    matches = re.findall(r"Time to do nbstatus jobs --target (\S+) is high, with a value of (\d+) ", text, re.IGNORECASE)
    if matches:
        out["info2"] = ", ".join(f"{target} - {value}" for target, value in matches)
    else:
        dprint("NetBatchQos parser: no match")

    return out

def parse_swapping_compute():
    global soup
    dprint(f"[PARSER] parse_swapping_compute")
    text = soup.get_text(" ", strip=True)
    out = {}

    rgxstr1 = r"machine\s+(\S+)\s+is\s+swapping\s+at\s*(\S+)\s*"
    rgxstr2 = r''
    out["info1"] = getdata_p(rgxstr1, all=False)
    out["info2"] = getdata_tbl1(cols=[11], rgxstr=rgxstr2, red=True, compress=True)



    return out

def parse_license_low_availability():
    global soup
    dprint(f"[PARSER] parse_license_low_availability")
    text = soup.get_text(" ", strip=True)
    out = {}
    match = re.search(r"license\s+low\s+availability\s+on\s+(\s+)", text, re.IGNORECASE)
    if match:
        out["info2"] = match.group(1)

    return out

def subject_startswith(prefix):
    return lambda subject: subject.startswith(prefix)


def subject_contains(fragment):
    return lambda subject: fragment in subject

def parse_with_regex_lists( ):
    """
    Default parser with two lists of regex patterns.
    Tries each regex in order, stops at first match.
    Only searches in <p> elements like getdata_p().
    """

    info1_regexes = [r'average response time of (\S+ \S+)', r'summary:\s*(\S+) from (\S+) will fill in']
    info2_regexes = [r'nbstatus jobs --target (\S+) is high',r'sname\s*: (\S+)']
    info1_result = ""
    # Try each regex in info1_regexes, stop at first match
    for rgx in info1_regexes:
        result = getdata_p(rgx, all=True)  # all=False stops at first match
        if result:
            info1_result = result
            break
    
    info2_result = ""
    # Try each regex in info2_regexes, stop at first match
    for rgx in info2_regexes:
        result = getdata_p(rgx, all=True)  # all=False stops at first match
        dprint(f"[DEBUG] Trying regex '{rgx}' got result: {result}")
        if result:
            info2_result = result
            break
    
    return {
        "info1": info1_result,
        "info2": info2_result,
    }

PARSER_RULES = [
    (subject_startswith("alertrouter: critical"), parse_critical),
    (subject_startswith("alertrouter: warning emergency rampdown is firing"), parse_emergency_rampdown),
    (subject_startswith("swapping compute"), parse_swapping_compute),
    (subject_startswith("alertrouter: warning ttd_netapp_aggr_full is firing"), parse_ttd_netapp_aggr),
    (subject_startswith("alertrouter: warning ito_aggr_will_fill_in_x_days is firing"), parse_aggr_will_fill),
    (subject_startswith("alertrouter: warning ttd_ref_volume_full is firing"), parse_ttd_ref_vol_fill),
    #    (subject_startswith("alertrouter: warning ito_vol_will_fill_in_x_days is firing"), parse_ito_vol_fill),
    (subject_startswith("alertrouter: critical its alert"), parse_critical_its),
    (subject_startswith("alertrouter: warning licenselowavailability is firing"), parse_license_low_availability),
    #(subject_startswith("alertrouter: warning computehighload is firing"), parse_computehighload),
    #(subject_startswith("alertrouter: warning netbatchqos is firing"), parse_netbatchqos),
    (subject_contains("highnbjobwaitcountbyclass"), parse_high_nb_job_wait),
    (lambda subject: True, parse_with_regex_lists),  # Default catch-all
]


def parse_email_by_subject(subject, html, raw_subject=None):
    global soup, raw_subject_cache
    soup = BeautifulSoup(html, "html.parser")
    raw_subject_cache = raw_subject or subject
    match_subject = raw_subject_cache
    parsed = default_parse_result()
    parsed.update(get_common_links())

    for matcher, parser_func in PARSER_RULES:
        if matcher(match_subject):
            parsed.update(parser_func())
            return parsed

    parsed.update(parse_base())
    return parsed
def load_existing_json(path):
    """Loads existing data to preserve manual status/notes."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}
def build_combined_data(allfiles):
    # 1. Load existing data
    global soup
    combined_data = load_existing_json(OUTPUT_JSON)
    
    for file in allfiles:
        item_id = os.path.basename(file)
        htmlfile = f"{file}.html"
        rewrite_email(htmlfile)
        
        # Extract subject from HTML <p class="subject">
        html = load_html_file(htmlfile)
        dprint(f"[DEBUG] Loaded HTML: {htmlfile[:60]}... (length: {len(html) if html else 0})")
        
        subject = ""
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            elem = soup.select_one('p.subject')
            if elem:
                subject = elem.get_text(strip=True).replace('Subject:', '').strip()
                dprint(f"[DEBUG] Subject extracted: {subject[:60]}...")
            else:
                dprint(f"[WARNING] No <p class='subject'> found in HTML")
        else:
            dprint(f"[ERROR] Failed to load HTML file: {htmlfile}")
        
        subject, server = cleanupsubject(subject)
        dprint(f"[INFO] Processing HTML: {htmlfile} | Subject: {subject[:50] if subject else 'EMPTY'} | Server: {server}")
        # Ensure subject key exists
        if subject not in combined_data:
            combined_data[subject] = {
                "ind_dats": {},
                "rfc": "", "dashboard": "", "notes": "", "info": ""
            }
        
        # Extract timestamp from HTML <p class="timestamp">
        timestamp_elem = soup.select_one('p.timestamp') if soup else None
        datetime_str = timestamp_elem.get_text(strip=True).replace('Sent:', '').strip() if timestamp_elem else ""
        dprint(f"[DEBUG] Timestamp: {datetime_str if datetime_str else 'NOT FOUND'}")
        
        # Prepare new data from parser
        new_ind_dat = {
            "info1": "", "info2": "", "path": "", 
            "status": "", "link":  f"http://localhost:5000/triagemails/{item_id}.html",
            "notes":"","users":"",
            "datetime":convert_datetime(datetime_str)
        }
        
        if html:
            dprint(f"[DEBUG] Parsing email content...")
            parsed = parse_email_by_subject(subject, html, raw_subject=subject)
            new_ind_dat.update({
                "info1": parsed["info1"],
                "info2": parsed["info2"],
                "path": parsed["path"],
                "notes": parsed["notes"],
                "users": parsed["users"],
            })
            
            # Preserve/Update RFC/Dashboard if empty
            if not combined_data[subject]["rfc"]:
                combined_data[subject]["rfc"] = parsed["rfc"]
            if not combined_data[subject]["dashboard"]:
                combined_data[subject]["dashboard"] = parsed["dashboard"]
        
            
        # 2. MERGE LOGIC:
        if item_id in combined_data[subject]["ind_dats"]:
            # Update existing: Keep status, update all other fields including new ones
            existing_entry = combined_data[subject]["ind_dats"][item_id]
            # Preserve existing status if it exists
            existing_status = existing_entry.get("status", "")
            
            # Update with all new data
            existing_entry.update({
                "info1": new_ind_dat["info1"],
                "info2": new_ind_dat["info2"],
                "path": new_ind_dat["path"],
                "link": new_ind_dat["link"],
                "notes": new_ind_dat["notes"],
                "users": new_ind_dat["users"],
                "datetime": new_ind_dat["datetime"]
            })
            
            # Restore status if it was previously set
            if existing_status:
                existing_entry["status"] = existing_status
            dprint(f"[DEBUG] Updated existing entry for ID: {item_id}")
        else:
            # Add new entry
            combined_data[subject]["ind_dats"][item_id] = new_ind_dat
            dprint(f"[DEBUG] Added new entry for ID: {item_id}")
            
        # Keep subject notes if they weren't already there
        if not combined_data[subject]["notes"]:
            combined_data[subject]["notes"] = ""  # Notes extracted from HTML if available
    return combined_data
def main():
    allfiles = get_files_from_text()
    dprint(f"[INFO] Starting processing of {len(allfiles)} files...")
    
    combined_data = build_combined_data(allfiles)
    
    dprint(f"[INFO] Total subjects processed: {len(combined_data)}")
    save_json(combined_data, OUTPUT_JSON)
    
    dprint(f"[OK] Merged data saved to: {OUTPUT_JSON}")

if __name__=="__main__":
    #rewrite_email()
    main()
