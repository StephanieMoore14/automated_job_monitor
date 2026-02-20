#!/usr/bin/env python3
"""
WHOOP Job Monitor V3
Monitors specific departments on the WHOOP careers page.
Simplified approach: Extract all jobs, then filter by department.
"""

import json
import os
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("⚠️  Selenium not installed. Run: pip install selenium")

# Configuration
CAREERS_URL = "https://www.whoop.com/us/en/careers/"
CHECK_INTERVAL = 3600  # Check every hour (in seconds)
DATA_FILE = Path("whoop_jobs_data.json")

# Schedule: every day at 8:00 AM Eastern (EST/EDT)
SCHEDULE_SLOTS = [(d, 8, 0) for d in range(7)]  # All weekdays, 8am
EASTERN = ZoneInfo("America/New_York")


def get_next_run_time():
    """Return the next datetime (Eastern) when the script should run."""
    now = datetime.now(EASTERN)
    next_runs = []
    for days_ahead in range(8):
        day = now + timedelta(days=days_ahead)
        for weekday, hour, minute in SCHEDULE_SLOTS:
            if day.weekday() == weekday:
                run_time = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if run_time > now:
                    next_runs.append(run_time)
    return min(next_runs) if next_runs else None

# DEPARTMENTS TO MONITOR - Only track jobs in these departments
DEPARTMENTS_TO_MONITOR = [
    "Data Science & Research",
    "Performance Science"
]


class WhoopJobMonitor:
    def __init__(self, notification_method):
        """
        Initialize the job monitor.
        
        Args:
            notification_method: How to notify ('console', 'email', or 'both')
        """
        self.notification_method = notification_method
        self.previous_jobs = self.load_previous_jobs()
        
    def load_previous_jobs(self):
        """Load previously saved job data."""
        if DATA_FILE.exists():
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    def save_jobs(self, jobs):
        """Save current job data."""
        with open(DATA_FILE, 'w') as f:
            json.dump(jobs, f, indent=2)
    
    def setup_driver(self):
        """Setup Chrome driver with headless mode."""
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # Run in background
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            return driver
        except Exception as e:
            print(f"❌ Error setting up Chrome driver: {e}")
            print("\n💡 You need to install ChromeDriver:")
            print("   1. Download from: https://googlechromelabs.github.io/chrome-for-testing/")
            print("   2. Or install via: pip install webdriver-manager")
            print("   3. Make sure Chrome browser is installed\n")
            return None
    
    def fetch_jobs(self):
        """
        Fetch current job listings from WHOOP careers page using Selenium.
        
        Returns:
            dict: Dictionary of job listings filtered by monitored departments
        """
        if not SELENIUM_AVAILABLE:
            print("❌ Selenium is required. Install with: pip install selenium")
            return {}
        
        driver = self.setup_driver()
        if not driver:
            return {}
        
        try:
            print("🌐 Loading WHOOP careers page...")
            driver.get(CAREERS_URL)
            
            # Wait for the Lever integration to load
            print("⏳ Waiting for Lever job board integration to load...")
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "lever-integration-table"))
                )
                print("   ✓ Lever container found")
                
                time.sleep(5)
                
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "accordion-table_accordion-table__header__VM2KA"))
                )
                print("   ✓ Job accordions loaded")
                
            except Exception as wait_error:
                print(f"   ⚠️  Timeout waiting for jobs to load: {wait_error}")
            
            jobs = {'listings': [], 'departments': {}, 'all_departments': {}}
            
            # Step 1: Get all department info and click ALL accordions to expand them
            print(f"\n📂 Expanding all accordions to load job data...")
            try:
                accordion_headers = driver.find_elements(By.CSS_SELECTOR, 
                    ".accordion-table_accordion-table__header__VM2KA")
                
                print(f"   Found {len(accordion_headers)} total departments")
                
                for header in accordion_headers:
                    try:
                        dept_name_elem = header.find_element(By.CSS_SELECTOR, ".text_text--size-lg__uWJQC")
                        dept_name = dept_name_elem.text.strip()
                        
                        dept_count_elem = header.find_element(By.CSS_SELECTOR, ".text_text--size-md__z_JDN")
                        dept_count = dept_count_elem.text.strip()
                        
                        if dept_name:
                            jobs['all_departments'][dept_name] = dept_count
                            
                            # Click to expand - try JavaScript click which is more reliable
                            try:
                                driver.execute_script("arguments[0].click();", header)
                                time.sleep(0.3)
                            except:
                                pass
                    except:
                        continue
                
                print(f"   Waiting for content to load...")
                time.sleep(3)
                
            except Exception as e:
                print(f"   ⚠️  Error expanding accordions: {e}")
            
            # Step 2: Extract ALL job titles from the page
            print(f"\n🔍 Extracting all job listings from page...")
            
            try:
                job_elements = driver.find_elements(By.CSS_SELECTOR, 
                    "span.accordion-table_table__cell__puVO3.accordion-table_table__cell--first__vBzOR")
                
                print(f"   Found {len(job_elements)} total job elements")
                
                # We need to map jobs to departments
                # Strategy: Get parent section and find the department header within it
                for elem in job_elements:
                    try:
                        # Get job title
                        job_title = elem.text.strip()
                        
                        if not job_title:
                            nested_spans = elem.find_elements(By.CSS_SELECTOR, "span")
                            for span in nested_spans:
                                text = span.text.strip()
                                if text and len(text) > 5:
                                    job_title = text
                                    break
                        
                        if not job_title:
                            job_title = driver.execute_script("return arguments[0].textContent;", elem).strip()
                        
                        # Skip non-job text
                        skip_words = ['doha', 'boston', 'onsite', 'remote', 'hybrid', 'flex', 'location']
                        if not job_title or len(job_title) <= 5:
                            continue
                        if job_title.lower() in skip_words or job_title.lower().startswith('location'):
                            continue
                        
                        # Try to determine which department this job belongs to
                        # Find the closest ancestor section that contains a department header
                        department = None
                        try:
                            # Go up the DOM tree to find the section
                            parent = elem
                            for _ in range(10):  # Try up to 10 levels up
                                parent = parent.find_element(By.XPATH, "./parent::*")
                                try:
                                    # Look for department header in this parent
                                    dept_header = parent.find_element(By.CSS_SELECTOR, 
                                        ".accordion-table_accordion-table__header__VM2KA .text_text--size-lg__uWJQC")
                                    department = dept_header.text.strip()
                                    break
                                except:
                                    continue
                        except:
                            pass
                        
                        # Get job URL
                        try:
                            parent_link = elem.find_element(By.XPATH, "./ancestor::a")
                            job_url = parent_link.get_attribute('href')
                        except:
                            job_url = CAREERS_URL
                        
                        # Store the job with its department
                        job_data = {
                            'title': job_title,
                            'url': job_url,
                            'department': department
                        }
                        
                        # Avoid duplicates
                        if not any(j['title'] == job_title for j in jobs['listings']):
                            jobs['listings'].append(job_data)
                    
                    except Exception as e:
                        continue
                
            except Exception as e:
                print(f"   ⚠️  Error extracting jobs: {e}")
            
            # Step 3: Filter to only monitored departments
            print(f"\n🎯 Filtering jobs for monitored departments...")
            print(f"   Monitoring: {', '.join(DEPARTMENTS_TO_MONITOR)}")
            
            filtered_listings = []
            for job in jobs['listings']:
                if job['department'] in DEPARTMENTS_TO_MONITOR:
                    filtered_listings.append(job)
                    print(f"   ✓ {job['title']} ({job['department']})")
            
            # Only keep monitored departments in the departments dict
            for dept in DEPARTMENTS_TO_MONITOR:
                if dept in jobs['all_departments']:
                    jobs['departments'][dept] = jobs['all_departments'][dept]
            
            # Replace listings with filtered list
            jobs['listings'] = filtered_listings
            
            # Get page source for hash comparison
            page_source = driver.page_source
            jobs['page_hash'] = hashlib.md5(page_source.encode()).hexdigest()
            
            # Store metadata
            jobs['count'] = len(jobs['listings'])
            jobs['department_count'] = len(jobs['departments'])
            jobs['last_checked'] = datetime.now().isoformat()
            
            print(f"\n✅ Extracted {jobs['count']} jobs from {jobs['department_count']} monitored departments")
            
            return jobs
            
        except Exception as e:
            print(f"❌ Error fetching jobs: {e}")
            import traceback
            traceback.print_exc()
            return {}
        finally:
            driver.quit()
    
    def compare_with_previous(self, current_jobs):
        """
        Compare current jobs to the saved JSON (previous run).
        Returns dict with 'new' and 'removed' lists of job dicts.
        """
        prev_listings = self.previous_jobs.get('listings') or []
        curr_listings = current_jobs.get('listings') or []
        prev_titles = {j['title'] for j in prev_listings}
        curr_titles = {j['title'] for j in curr_listings}
        new_titles = curr_titles - prev_titles
        removed_titles = prev_titles - curr_titles
        new_jobs = [j for j in curr_listings if j['title'] in new_titles]
        removed_jobs = [j for j in prev_listings if j['title'] in removed_titles]
        return {'new': new_jobs, 'removed': removed_jobs}
    
    def format_current_jobs_report(self, jobs, changes_since_last=None):
        """Build the same report text used for console and email."""
        lines = []
        lines.append(f"\n{'='*70}")
        lines.append(f"📋 CURRENT JOB LISTINGS - WHOOP Careers")
        lines.append(f"🎯 Monitoring: {', '.join(DEPARTMENTS_TO_MONITOR)}")
        lines.append(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"{'='*70}")
        
        # Changes since last run (JSON comparison)
        if changes_since_last and (changes_since_last['new'] or changes_since_last['removed']):
            lines.append(f"\n📌 CHANGES SINCE LAST RUN (vs saved JSON):\n")
            if changes_since_last['new']:
                lines.append(f"   ✨ NEW OPENINGS ({len(changes_since_last['new'])}):")
                for j in changes_since_last['new']:
                    dept = j.get('department') or '?'
                    lines.append(f"      • {j['title']} [{dept}]")
                    if j.get('url') and j['url'] != CAREERS_URL:
                        lines.append(f"        🔗 {j['url']}")
                lines.append("")
            if changes_since_last['removed']:
                lines.append(f"   ❌ REMOVED / FILLED ({len(changes_since_last['removed'])}):")
                for j in changes_since_last['removed']:
                    dept = j.get('department') or '?'
                    lines.append(f"      • {j['title']} [{dept}]")
                lines.append("")
        elif changes_since_last and not changes_since_last['new'] and not changes_since_last['removed']:
            lines.append(f"\n📌 No changes since last run (same listings as saved JSON).\n")
        
        if 'departments' in jobs and jobs['departments']:
            lines.append(f"\n📂 MONITORED DEPARTMENTS ({len(jobs['departments'])} total):\n")
            for dept, count in jobs['departments'].items():
                lines.append(f"   • {dept}: {count}")
        
        if 'listings' in jobs and jobs['listings']:
            lines.append(f"\n💼 OPEN POSITIONS IN MONITORED DEPARTMENTS ({jobs['count']} total):\n")
            for i, job in enumerate(jobs['listings'], 1):
                dept_label = f" [{job.get('department', '?')}]" if job.get('department') else ""
                lines.append(f"{i}. {job['title']}{dept_label}")
                if job['url'] != CAREERS_URL:
                    lines.append(f"   🔗 {job['url']}")
                lines.append("")
        else:
            lines.append(f"\n⚠️  No job listings found in monitored departments.")
            lines.append(f"   Visit the careers page directly: {CAREERS_URL}\n")
        
        if 'last_checked' in jobs:
            lines.append(f"Last checked: {jobs['last_checked']}")
        
        lines.append(f"{'='*70}\n")
        return "\n".join(lines)
    
    def display_current_jobs(self, jobs):
        """Display the current job listings (console)."""
        print(self.format_current_jobs_report(jobs))
    
    def send_notification(self, report_message, has_new_jobs=False):
        """Send the same report to console and/or email."""
        if self.notification_method in ['console', 'both']:
            print(report_message)
        
        if self.notification_method in ['email', 'both']:
            self.send_email_notification(report_message, has_new_jobs=has_new_jobs)
    
    def send_email_notification(self, message, has_new_jobs=False):
        """Send email notification (same content as console report)."""
        # Email config: use env vars in CI (GitHub Actions secrets), else fallback to defaults
        smtp_server = os.environ.get("WHOOP_SMTP_SERVER") or "smtp.gmail.com"
        smtp_port = int(os.environ.get("WHOOP_SMTP_PORT") or "587")
        sender_email = os.environ.get("WHOOP_SENDER_EMAIL") or "sgmoore209@gmail.com"
        sender_password = os.environ.get("WHOOP_SMTP_PASSWORD") or "qnqkowjouucedivr"
        receiver_email = os.environ.get("WHOOP_RECEIVER_EMAIL") or "sgmoore209@gmail.com"
        
        subject = "📋 WHOOP Careers - NEW Job Listings" if has_new_jobs else "📋 WHOOP Careers - Current Job Listings"
        
        try:
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = receiver_email
            msg['Subject'] = subject
            
            msg.attach(MIMEText(message, 'plain'))
            
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
            
            print("📧 Email notification sent successfully!")
            
        except Exception as e:
            print(f"❌ Failed to send email: {e}")
    
    def run_once(self):
        """Run a single check for new jobs."""
        print(f"Checking WHOOP careers page at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")
        
        current_jobs = self.fetch_jobs()
        
        if current_jobs:
            # Compare with saved JSON (previous run) for new/removed jobs
            changes = self.compare_with_previous(current_jobs) if self.previous_jobs.get('listings') else None
            has_new_jobs = changes and len(changes.get('new', [])) > 0
            # Build report including changes since last run (omit on first run)
            report = self.format_current_jobs_report(current_jobs, changes_since_last=changes)
            self.send_notification(report, has_new_jobs=has_new_jobs)
            
            # Save current state to JSON for next comparison
            self.previous_jobs = current_jobs
            self.save_jobs(current_jobs)
        else:
            print("❌ Failed to fetch job data.")
    
    def run_continuous(self):
        """Run continuous monitoring."""
        print(f"Starting WHOOP job monitor...")
        print(f"Checking every {CHECK_INTERVAL} seconds ({CHECK_INTERVAL/3600:.1f} hours)")
        print(f"Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.run_once()
                print(f"\n⏰ Next check in {CHECK_INTERVAL} seconds ({CHECK_INTERVAL/60:.0f} minutes)...\n")
                time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\n\n✋ Monitoring stopped by user.")
    
    def run_scheduled(self):
        """Run every day at 8am Eastern. Sleeps until the next scheduled time."""
        print("Starting WHOOP job monitor (scheduled: every day at 8:00 AM Eastern)")
        print(f"Press Ctrl+C to stop\n")
        try:
            while True:
                next_run = get_next_run_time()
                if not next_run:
                    print("❌ Could not determine next run time.")
                    break
                now = datetime.now(EASTERN)
                wait_seconds = (next_run - now).total_seconds()
                if wait_seconds <= 0:
                    self.run_once()
                    continue
                print(f"⏰ Next run: {next_run.strftime('%A %Y-%m-%d at %I:%M %p')} Eastern (in {wait_seconds/3600:.1f} hours)")
                time.sleep(wait_seconds)
                self.run_once()
        except KeyboardInterrupt:
            print("\n\n✋ Scheduled monitoring stopped by user.")


def main():
    """Main function to run the job monitor."""
    # Choose notification method: 'console', 'email', or 'both'
    monitor = WhoopJobMonitor(notification_method='both')
    
    # In CI (e.g. GitHub Actions): run once and exit. Locally: use scheduled or one-off.
    if os.environ.get("RUN_ONCE"):
        monitor.run_once()
        return
    
    # For one-time check (when not using RUN_ONCE):
    # monitor.run_once()
    
    # For continuous monitoring (every CHECK_INTERVAL seconds):
    # monitor.run_continuous()
    
    # Scheduled: every day at 8am Eastern
    monitor.run_scheduled()


if __name__ == "__main__":
    main()