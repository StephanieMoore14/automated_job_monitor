# Fix Code Review Issues Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all Important and Minor issues flagged in the code review of `whoop_job_monitor.py`.

**Architecture:** All changes are confined to a single file (`whoop_job_monitor.py`) plus `.gitignore`. Each task is self-contained and can be applied independently. No new files or dependencies are introduced.

**Tech Stack:** Python 3, Selenium, standard library only.

---

## Task 1: Add `whoop_jobs_data.json` to `.gitignore` (I3)

**Files:**
- Modify: `.gitignore:9-10`

**Why:** The state file is committed on every run, creating noisy diffs and leaking job data into PRs. The line already exists but is commented out.

- [ ] **Step 1: Uncomment the line in `.gitignore`**

Change:
```
# whoop_jobs_data.json
```
To:
```
whoop_jobs_data.json
```

- [ ] **Step 2: Verify git no longer tracks the file**

Run:
```bash
git check-ignore -v whoop_jobs_data.json
```
Expected output: `.gitignore:10:whoop_jobs_data.json    whoop_jobs_data.json`

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore whoop_jobs_data.json state file"
```

---

## Task 2: Replace bare `except: pass` with logged exceptions (I4)

**Files:**
- Modify: `whoop_job_monitor.py:163-167` (accordion click)
- Modify: `whoop_job_monitor.py:225-227` (department DOM traversal)
- Modify: `whoop_job_monitor.py:231-235` (job URL extraction)

**Why:** Bare `except: pass` silently swallows `KeyboardInterrupt` and `SystemExit` in addition to real errors, making scrape failures impossible to diagnose.

- [ ] **Step 1: Fix the accordion click bare except (line ~166)**

Change:
```python
try:
    driver.execute_script("arguments[0].click();", header)
    time.sleep(0.3)
except:
    pass
```
To:
```python
try:
    driver.execute_script("arguments[0].click();", header)
    time.sleep(0.3)
except Exception as e:
    print(f"   ⚠️  Could not click accordion for '{dept_name}': {e}")
```

- [ ] **Step 2: Fix the department DOM traversal bare except (line ~225)**

Change:
```python
                except:
                    continue
        except:
            pass
```
To:
```python
                except Exception:
                    continue
        except Exception:
            pass
```

- [ ] **Step 3: Fix the job URL extraction bare except (line ~234)**

Change:
```python
        try:
            parent_link = elem.find_element(By.XPATH, "./ancestor::a")
            job_url = parent_link.get_attribute('href')
        except:
            job_url = CAREERS_URL
```
To:
```python
        try:
            parent_link = elem.find_element(By.XPATH, "./ancestor::a")
            job_url = parent_link.get_attribute('href')
        except Exception:
            job_url = CAREERS_URL
```

- [ ] **Step 4: Commit**

```bash
git add whoop_job_monitor.py
git commit -m "fix: replace bare except clauses with explicit Exception handling"
```

---

## Task 3: Use `(title, department)` composite key for deduplication and comparison (I1)

**Files:**
- Modify: `whoop_job_monitor.py:244-246` (deduplication in `fetch_jobs`)
- Modify: `whoop_job_monitor.py:295-308` (`compare_with_previous`)

**Why:** Title-only matching silently drops jobs with identical titles in different departments, and misses re-posted roles (same title, new Lever URL after being filled).

- [ ] **Step 1: Update deduplication in `fetch_jobs` to use `(title, department)` key**

Change:
```python
# Avoid duplicates
if not any(j['title'] == job_title for j in jobs['listings']):
    jobs['listings'].append(job_data)
```
To:
```python
# Avoid duplicates using composite (title, department) key
if not any(j['title'] == job_title and j['department'] == department for j in jobs['listings']):
    jobs['listings'].append(job_data)
```

- [ ] **Step 2: Update `compare_with_previous` to use `(title, department)` composite keys**

Change:
```python
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
```
To:
```python
def compare_with_previous(self, current_jobs):
    """
    Compare current jobs to the saved JSON (previous run).
    Uses (title, department) composite key to correctly detect re-posted roles
    and jobs with identical titles in different departments.
    Returns dict with 'new' and 'removed' lists of job dicts.
    """
    prev_listings = self.previous_jobs.get('listings') or []
    curr_listings = current_jobs.get('listings') or []
    prev_keys = {(j['title'], j.get('department')) for j in prev_listings}
    curr_keys = {(j['title'], j.get('department')) for j in curr_listings}
    new_keys = curr_keys - prev_keys
    removed_keys = prev_keys - curr_keys
    new_jobs = [j for j in curr_listings if (j['title'], j.get('department')) in new_keys]
    removed_jobs = [j for j in prev_listings if (j['title'], j.get('department')) in removed_keys]
    return {'new': new_jobs, 'removed': removed_jobs}
```

- [ ] **Step 3: Commit**

```bash
git add whoop_job_monitor.py
git commit -m "fix: use (title, department) composite key for job deduplication and comparison"
```

---

## Task 4: Guard against saving a partial/empty scrape as the baseline (I5)

**Files:**
- Modify: `whoop_job_monitor.py:429-439` (`run_once`)

**Why:** A timed-out or partially-failed scrape can return a near-empty `listings` list that still evaluates as truthy. Saving it as the new baseline causes all real jobs to appear as "new" on the next run.

- [ ] **Step 1: Add a minimum job count check before saving in `run_once`**

Change:
```python
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
```
To:
```python
        if current_jobs.get('count', 0) > 0:
            # Compare with saved JSON (previous run) for new/removed jobs
            changes = self.compare_with_previous(current_jobs)
            has_new_jobs = len(changes.get('new', [])) > 0
            # Build report including changes since last run
            report = self.format_current_jobs_report(current_jobs, changes_since_last=changes)
            self.send_notification(report, has_new_jobs=has_new_jobs)

            # Save current state to JSON for next comparison
            self.previous_jobs = current_jobs
            self.save_jobs(current_jobs)
        elif current_jobs:
            # Scrape ran but returned zero listings — likely a page load failure.
            # Do NOT save this as the new baseline to avoid false "all jobs new" on next run.
            print("⚠️  Scrape returned 0 jobs — skipping save to preserve previous baseline.")
            changes = self.compare_with_previous(current_jobs)
            report = self.format_current_jobs_report(current_jobs, changes_since_last=changes)
            self.send_notification(report, has_new_jobs=False)
        else:
            print("❌ Failed to fetch job data.")
```

Note: This also removes the `if self.previous_jobs.get('listings') else None` guard, so `compare_with_previous` is now always called (fixing I2 — the asymmetric first-run guard). On first run with no previous data, it correctly returns `{'new': [], 'removed': []}`.

- [ ] **Step 2: Commit**

```bash
git add whoop_job_monitor.py
git commit -m "fix: skip saving baseline when scrape returns 0 jobs; always compare with previous"
```

---

## Task 5: Add department name mismatch warning on startup (M4)

**Files:**
- Modify: `whoop_job_monitor.py` — add warning inside `fetch_jobs` after Step 3 filter

**Why:** If WHOOP renames a department, the filter silently stops matching and all jobs appear removed. A clear warning on zero matches makes this easy to diagnose.

- [ ] **Step 1: Add warning when a monitored department matches zero scraped departments**

After the existing filter block (after line ~269, the `jobs['departments']` population loop), add:

```python
            # Warn if a monitored department name doesn't match any scraped department
            for dept in DEPARTMENTS_TO_MONITOR:
                if dept not in jobs['all_departments']:
                    print(f"   ⚠️  WARNING: Monitored department '{dept}' not found on page.")
                    print(f"        Available departments: {list(jobs['all_departments'].keys())}")
```

- [ ] **Step 2: Commit**

```bash
git add whoop_job_monitor.py
git commit -m "fix: warn when monitored department name not found on careers page"
```

---

## Task 6: Remove unused `page_hash` and add `CHECK_INTERVAL` clarifying comment (M1, M2)

**Files:**
- Modify: `whoop_job_monitor.py:10` (remove `hashlib` import)
- Modify: `whoop_job_monitor.py:274-276` (remove `page_hash` computation)
- Modify: `whoop_job_monitor.py:32` (add comment to `CHECK_INTERVAL`)

**Why:** Dead code creates confusion about what the comparison logic actually uses. `CHECK_INTERVAL` is only relevant to `run_continuous`, not the default `run_scheduled` path.

- [ ] **Step 1: Remove the `hashlib` import (line 10)**

Change:
```python
import hashlib
```
To: *(delete the line entirely)*

- [ ] **Step 2: Remove `page_hash` computation in `fetch_jobs` (lines ~274-276)**

Change:
```python
            # Get page source for hash comparison
            page_source = driver.page_source
            jobs['page_hash'] = hashlib.md5(page_source.encode()).hexdigest()

            # Store metadata
```
To:
```python
            # Store metadata
```

- [ ] **Step 3: Add clarifying comment to `CHECK_INTERVAL` (line ~32)**

Change:
```python
CHECK_INTERVAL = 3600  # Check every hour (in seconds)
```
To:
```python
CHECK_INTERVAL = 3600  # Check every hour (in seconds) — used by run_continuous() only, not run_scheduled()
```

- [ ] **Step 4: Commit**

```bash
git add whoop_job_monitor.py
git commit -m "chore: remove unused page_hash/hashlib; clarify CHECK_INTERVAL comment"
```
