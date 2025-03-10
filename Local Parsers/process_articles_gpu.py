#!/usr/bin/env python3
import os
import sys
import shutil
import json
import datetime
import glob
import subprocess
import time
import traceback

# Global log for collecting messages
log_messages = []

def log(message, level="INFO"):
    """Log a message and print it"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{level}] {timestamp} - {message}"
    print(formatted)
    log_messages.append({"level": level, "message": message, "timestamp": timestamp})

def prepare_gpu_processing():
    """
    Prepare directories for GPU-based NLP processing
    """
    # Base directories
    base_dir = '/home/n8n'
    input_dir = os.path.join(base_dir, 'Output')
    gpu_input_dir = os.path.join(base_dir, 'gpu_input_articles')
    gpu_output_dir = os.path.join(base_dir, 'gpu_processed_articles')
    
    # Create directories if they don't exist
    os.makedirs(gpu_input_dir, exist_ok=True)
    os.makedirs(gpu_output_dir, exist_ok=True)
    log(f"Created or verified directories: {gpu_input_dir}, {gpu_output_dir}")
    
    # Clean previous input files
    removed_count = 0
    for existing_file in glob.glob(os.path.join(gpu_input_dir, '*')):
        os.remove(existing_file)
        removed_count += 1
    log(f"Cleaned {removed_count} previous files from {gpu_input_dir}")
    
    # Find HTML files in the input directory
    html_files = glob.glob(os.path.join(input_dir, '*.html'))
    
    if not html_files:
        log(f"No HTML files found in {input_dir}", "WARNING")
        return False
    
    # Copy HTML files to GPU processing directory
    for file in html_files:
        shutil.copy(file, gpu_input_dir)
    
    log(f"Copied {len(html_files)} HTML files to GPU processing directory")
    return True

def check_python_path():
    """
    Check for Python path on the remote machine
    """
    vastai_host = "70.26.213.157"
    vastai_port = "6297"
    ssh_key_path = "/home/n8n/.ssh/vastai_instance_key"
    
    # Check if SSH key exists
    if not os.path.exists(ssh_key_path):
        log(f"SSH key not found at {ssh_key_path}", "ERROR")
        return None
    
    # Check for Python paths
    cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} 'which python3; which python; ls -la /usr/bin/python*; echo PATH=$PATH'"
    log("Checking Python paths...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"SSH command failed: {result.stderr}", "ERROR")
        return None
        
    log(f"Python paths on remote server: {result.stdout}")
    
    # Determine the best Python command to use
    if "python3" in result.stdout:
        return "python3"
    elif "python" in result.stdout:
        return "python"
    else:
        # Find any Python executable in the output
        for line in result.stdout.splitlines():
            if "python" in line and "->" not in line:
                path = line.split()[-1]
                if os.path.basename(path).startswith("python"):
                    return path
    
    # Default fallback
    log("Using default Python path: /usr/bin/python3", "WARNING")
    return "/usr/bin/python3"

def install_required_packages(python_cmd):
    """
    Install required Python packages on the vast.ai instance
    """
    if not python_cmd:
        log("No Python command provided for package installation", "ERROR")
        return False
        
    vastai_host = "70.26.213.157"
    vastai_port = "6297"
    ssh_key_path = "/home/n8n/.ssh/vastai_instance_key"
    
    log("Installing required Python packages on vast.ai instance...")
    
    # Install basic packages
    base_packages = "spacy torch transformers beautifulsoup4 tqdm numpy pandas"
    install_cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} '{python_cmd} -m pip install {base_packages}'"
    log(f"Running package installation: {install_cmd}")
    install_result = subprocess.run(install_cmd, shell=True, capture_output=True, text=True)
    
    if install_result.returncode != 0:
        log(f"Package installation failed: {install_result.stderr}", "WARNING")
        return False
    else:
        log("Base packages installation successful")
    
    # Install spaCy language model
    spacy_cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} '{python_cmd} -m spacy download en_core_web_lg'"
    log(f"Installing spaCy language model: {spacy_cmd}")
    spacy_result = subprocess.run(spacy_cmd, shell=True, capture_output=True, text=True)
    
    if spacy_result.returncode != 0:
        log(f"spaCy model installation failed: {spacy_result.stderr}", "WARNING")
        # Try with direct pip install as fallback
        alt_cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} '{python_cmd} -m pip install en-core-web-sm'"
        log(f"Trying fallback model installation: {alt_cmd}")
        alt_result = subprocess.run(alt_cmd, shell=True, capture_output=True, text=True)
        
        if alt_result.returncode != 0:
            log("All model installation attempts failed", "WARNING")
            return False
    
    log("Package installation completed")
    return True

def run_gpu_nlp_processing():
    """
    Run NLP processing on the GPU
    """
    base_dir = '/home/n8n'
    gpu_input_dir = os.path.join(base_dir, 'gpu_input_articles')
    gpu_output_dir = os.path.join(base_dir, 'gpu_processed_articles')
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Define vastai connection parameters
    vastai_host = "70.26.213.157"
    vastai_port = "6297"
    ssh_key_path = "/home/n8n/.ssh/vastai_instance_key"
    
    # Check if SSH key exists
    if not os.path.exists(ssh_key_path):
        log(f"SSH key not found at {ssh_key_path}", "ERROR")
        return None
    
    # Check for Python
    python_cmd = check_python_path()
    if not python_cmd:
        log("Failed to determine Python command on remote server", "ERROR")
        return None
        
    log(f"Using Python command: {python_cmd}")
    
    # Install required packages
    install_required_packages(python_cmd)
    
    # Create remote directories
    mkdir_cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} 'mkdir -p /workspace/input /workspace/output'"
    log(f"Creating remote directories: {mkdir_cmd}")
    mkdir_result = subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True)
    
    if mkdir_result.returncode != 0:
        log(f"Failed to create remote directories: {mkdir_result.stderr}", "ERROR")
        return None
    
    # Check if input files exist locally
    input_files = glob.glob(os.path.join(gpu_input_dir, '*'))
    if not input_files:
        log(f"No input files found in {gpu_input_dir}", "ERROR")
        return None
    
    # Copy files to vast.ai instance
    log("Copying HTML files to vast.ai instance...")
    scp_cmd = f"scp -i {ssh_key_path} -P {vastai_port} {gpu_input_dir}/* root@{vastai_host}:/workspace/input/"
    log(f"Running file transfer: {scp_cmd}")
    scp_result = subprocess.run(scp_cmd, shell=True, capture_output=True, text=True)
    
    if scp_result.returncode != 0:
        log(f"File transfer failed: {scp_result.stderr}", "ERROR")
        return None
    
    # Copy the NLP script to vast.ai
    scp_script_cmd = f"scp -i {ssh_key_path} -P {vastai_port} {base_dir}/nlp_extractor_gpu.py root@{vastai_host}:/workspace/"
    log(f"Transferring NLP script: {scp_script_cmd}")
    scp_script_result = subprocess.run(scp_script_cmd, shell=True, capture_output=True, text=True)
    
    if scp_script_result.returncode != 0:
        log(f"NLP script transfer failed: {scp_script_result.stderr}", "ERROR")
        return None
    
    # Run the NLP processing on vast.ai with explicit command
    log("Running NLP processing on GPU...")
    output_file = f"processed_results_{timestamp}.json"
    
    # Check if conda or other environments are available
    env_cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} 'ls -la /opt/conda/bin 2>/dev/null || echo \"No conda\"; echo $PATH'"
    env_result = subprocess.run(env_cmd, shell=True, capture_output=True, text=True)
    log(f"Environment check results: {env_result.stdout}")
    
    # Try with conda Python if available
    if "/opt/conda/bin" in env_result.stdout and "No conda" not in env_result.stdout:
        python_path = "/opt/conda/bin/python"
        log("Using conda Python for processing")
    else:
        python_path = python_cmd
        log(f"Using system Python for processing: {python_cmd}")
    
    # Execute NLP processing
    ssh_cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} '{python_path} /workspace/nlp_extractor_gpu.py /workspace/input /workspace/output/{output_file}'"
    log(f"Executing NLP processing: {ssh_cmd}")
    process_result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True)
    
    if process_result.returncode != 0:
        log(f"NLP processing failed: {process_result.stderr}", "ERROR")
        log(f"Process output: {process_result.stdout}", "INFO")
        return None
    
    # Wait and check for output file
    log("Waiting for processing to complete...")
    time.sleep(10)  # Increased wait time
    
    # Check if output file exists
    check_cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} 'ls -la /workspace/output/'"
    check_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
    log(f"Output directory contents: {check_result.stdout}")
    
    # Try to locate our specific output file
    file_check_cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} 'ls -la /workspace/output/{output_file}'"
    file_check_result = subprocess.run(file_check_cmd, shell=True, capture_output=True, text=True)
    
    # If our file doesn't exist, look for any JSON files
    if file_check_result.returncode != 0:
        log(f"Specific output file {output_file} not found", "WARNING")
        fallback_cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} 'find /workspace/output -name \"*.json\" -type f'"
        fallback_result = subprocess.run(fallback_cmd, shell=True, capture_output=True, text=True)
        
        if fallback_result.stdout.strip():
            # Use the first JSON file found
            fallback_file = fallback_result.stdout.strip().split('\n')[0]
            log(f"Found alternative JSON file: {fallback_file}")
            
            # Extract just the filename for local storage
            fallback_filename = os.path.basename(fallback_file)
            local_fallback = os.path.join(gpu_output_dir, fallback_filename)
            
            # Copy this file instead
            alt_copy_cmd = f"scp -i {ssh_key_path} -P {vastai_port} root@{vastai_host}:{fallback_file} {local_fallback}"
            log(f"Copying alternative file: {alt_copy_cmd}")
            alt_copy_result = subprocess.run(alt_copy_cmd, shell=True, capture_output=True, text=True)
            
            if alt_copy_result.returncode == 0:
                log(f"Successfully copied alternative file to {local_fallback}")
                return fallback_filename
            else:
                log(f"Failed to copy alternative file: {alt_copy_result.stderr}", "ERROR")
        else:
            log("No JSON output files found on remote server", "ERROR")
    
    # Copy results back
    copy_back_cmd = f"scp -i {ssh_key_path} -P {vastai_port} root@{vastai_host}:/workspace/output/{output_file} {gpu_output_dir}/"
    log(f"Copying results back: {copy_back_cmd}")
    copy_result = subprocess.run(copy_back_cmd, shell=True, capture_output=True, text=True)
    
    if copy_result.returncode != 0:
        log(f"Failed to copy results: {copy_result.stderr}", "ERROR")
        return None
    
    log(f"Successfully copied results to {gpu_output_dir}/{output_file}")
    return output_file

def move_processed_results():
    """
    Move processed results back to the original server
    """
    base_dir = '/home/n8n'
    gpu_output_dir = os.path.join(base_dir, 'gpu_processed_articles')
    processed_articles_dir = os.path.join(base_dir, 'ProcessedArticles')
    
    # Create output directory if it doesn't exist
    os.makedirs(processed_articles_dir, exist_ok=True)
    log(f"Created or verified directory: {processed_articles_dir}")
    
    # Check if there are any result files
    result_files = glob.glob(os.path.join(gpu_output_dir, '*.json'))
    if not result_files:
        log("No result files found to move", "WARNING")
        return False
    
    # Move processed files
    for result_file in result_files:
        dest_file = os.path.join(processed_articles_dir, os.path.basename(result_file))
        try:
            shutil.copy(result_file, dest_file)
            log(f"Moved {result_file} to {dest_file}")
        except Exception as e:
            log(f"Error moving file {result_file}: {str(e)}", "ERROR")
    
    # Define vastai connection parameters
    vastai_host = "70.26.213.157"
    vastai_port = "6297"
    ssh_key_path = "/home/n8n/.ssh/vastai_instance_key"
    
    # Clean up files on vast.ai
    cleanup_cmd = f"ssh -i {ssh_key_path} -p {vastai_port} root@{vastai_host} 'rm -rf /workspace/input/* /workspace/output/*'"
    log(f"Cleaning up remote files: {cleanup_cmd}")
    cleanup_result = subprocess.run(cleanup_cmd, shell=True, capture_output=True, text=True)
    
    if cleanup_result.returncode != 0:
        log(f"Remote cleanup failed: {cleanup_result.stderr}", "WARNING")
    
    # Remove local input files after successful processing
    removed = 0
    for file in glob.glob(os.path.join(base_dir, 'Output', '*.html')):
        try:
            os.remove(file)
            removed += 1
        except Exception as e:
            log(f"Could not remove file {file}: {str(e)}", "WARNING")
    
    log(f"Removed {removed} processed HTML files from input directory")
    log("Cleanup completed")
    return True

def print_summary():
    """Print a summary of the execution"""
    errors = sum(1 for msg in log_messages if msg["level"] == "ERROR")
    warnings = sum(1 for msg in log_messages if msg["level"] == "WARNING")
    
    summary = {
        "total_messages": len(log_messages),
        "errors": errors,
        "warnings": warnings,
        "success": errors == 0,
        "log": log_messages
    }
    
    print("\n--- EXECUTION SUMMARY ---")
    print(f"Total log entries: {len(log_messages)}")
    print(f"Errors: {errors}")
    print(f"Warnings: {warnings}")
    print(f"Execution {'succeeded' if errors == 0 else 'failed with errors'}")
    
    return summary

def main():
    try:
        log("Starting GPU NLP processing workflow...")
        
        # Prepare articles for GPU processing
        if not prepare_gpu_processing():
            log("No articles to process", "WARNING")
            summary = print_summary()
            print(json.dumps({"status": "no_articles", "summary": summary}))
            return 0  # Return success for "no articles" case
        
        # Run NLP processing
        output_file = run_gpu_nlp_processing()
        
        if not output_file:
            log("NLP processing failed or no output was generated", "ERROR")
            summary = print_summary()
            print(json.dumps({"status": "processing_failed", "summary": summary}))
            return 1
        
        # Move processed results back
        if not move_processed_results():
            log("Failed to move results", "ERROR")
            summary = print_summary()
            print(json.dumps({"status": "move_failed", "summary": summary}))
            return 1
        
        log("GPU NLP processing completed successfully")
        summary = print_summary()
        print(json.dumps({"status": "success", "output_file": output_file, "summary": summary}))
        return 0
    
    except Exception as e:
        log(f"Critical error: {str(e)}", "ERROR")
        log(traceback.format_exc(), "ERROR")
        summary = print_summary()
        print(json.dumps({"status": "error", "error": str(e), "summary": summary}))
        return 1

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(json.dumps({"status": "critical_error", "error": str(e), "traceback": traceback.format_exc()}))
        sys.exit(1)