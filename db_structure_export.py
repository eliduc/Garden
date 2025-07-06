import sqlite3
from datetime import datetime
import os
import configparser
import paramiko
import tempfile
import getpass

# Remote connection variables
ssh_client = None
sftp_client = None
remote_mode = False
remote_db_path = None
local_temp_db = None

def show_progress(message, progress=0):
    """Show progress message (console-based for CLI tool)"""
    bar_length = 50
    filled_length = int(bar_length * progress / 100)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    print(f'\r{message} |{bar}| {progress:.1f}%', end='', flush=True)
    if progress >= 100:
        print()  # New line when complete

def choose_database_mode():
    """Choose between local and remote database"""
    global remote_mode, ssh_client, sftp_client, remote_db_path, local_temp_db
    
    print("Database Structure Export Tool")
    print("=" * 30)
    print("\nSelect database connection mode:")
    print("1. Local Database")
    print("2. Remote Database (SSH)")
    
    while True:
        try:
            choice = input("\nEnter choice (1-2): ").strip()
            if choice in ['1', '2']:
                break
            print("Invalid choice. Please enter 1 or 2.")
        except KeyboardInterrupt:
            print("\nExiting...")
            return False, None
    
    if choice == '1':
        # Local mode
        remote_mode = False
        db_file = input("Enter database filename [garden_sensors.db]: ").strip() or 'garden_sensors.db'
        if not os.path.exists(db_file):
            print(f"Error: Local database '{db_file}' not found!")
            return False, None
        print(f"Using local database: {db_file}")
        return True, db_file
    
    else:
        # Remote mode
        return setup_remote_connection()

def setup_remote_connection():
    """Setup remote SSH connection and database"""
    global ssh_client, sftp_client, remote_db_path, local_temp_db, remote_mode
    
    # Read config for default values
    config = configparser.ConfigParser()
    config_file = 'garden.ini'
    config.read(config_file)
    
    default_login = ""
    default_dir = ""
    default_db_file = "garden_sensors.db"
    try:
        default_login = config.get('Remote', 'login')
        default_dir = config.get('Remote', 'dir')
    except (configparser.NoSectionError, configparser.NoOptionError):
        pass
    
    print("\nRemote Database Connection Setup")
    print("-" * 35)
    
    # Get connection details
    login = input(f"Login (user@host) [{default_login}]: ").strip() or default_login
    if not login:
        print("Error: Login is required")
        return False, None
    
    if '@' not in login:
        print("Error: Login format should be username@hostname")
        return False, None
    
    username, hostname = login.split('@', 1)
    
    remote_dir = input(f"Remote directory [{default_dir}]: ").strip() or default_dir
    if not remote_dir:
        print("Error: Remote directory is required")
        return False, None
    
    db_filename = input(f"Database filename [{default_db_file}]: ").strip() or default_db_file
    
    # Get password
    password = getpass.getpass("Password: ")
    if not password:
        print("Error: Password is required")
        return False, None
    
    max_attempts = 3
    for attempt in range(max_attempts):
        print(f"\nConnecting to {hostname}... (Attempt {attempt + 1}/{max_attempts})")
        
        try:
            # Create SSH client
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect
            ssh_client.connect(hostname, username=username, password=password, compress=True)
            print("✓ SSH connection established")
            
            # Open SFTP
            sftp_client = ssh_client.open_sftp()
            print("✓ SFTP connection established")
            
            # Check remote database
            remote_db_path = os.path.join(remote_dir, db_filename).replace('\\', '/')
            
            try:
                file_stat = sftp_client.stat(remote_db_path)
                file_size = file_stat.st_size
                file_size_mb = file_size / (1024 * 1024)
                print(f"✓ Found remote database ({file_size_mb:.1f} MB)")
                
            except FileNotFoundError:
                print(f"✗ Remote database '{remote_db_path}' not found!")
                return False, None
            
            # Download database
            print("Downloading database for analysis...")
            local_temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
            local_temp_db.close()
            
            def download_callback(transferred, total):
                progress = (transferred * 100 / total)
                show_progress("Downloading", progress)
            
            sftp_client.get(remote_db_path, local_temp_db.name, callback=download_callback)
            
            # Save settings to config
            if not config.has_section('Remote'):
                config.add_section('Remote')
            config.set('Remote', 'login', login)
            config.set('Remote', 'dir', remote_dir)
            
            with open(config_file, 'w') as f:
                config.write(f)
            
            print("✓ Remote database download complete!")
            remote_mode = True
            return True, local_temp_db.name
            
        except paramiko.AuthenticationException:
            print(f"✗ Authentication failed")
            if ssh_client:
                ssh_client.close()
                ssh_client = None
            
            if attempt < max_attempts - 1:
                print(f"Retrying... ({max_attempts - attempt - 1} attempts remaining)")
                password = getpass.getpass("Password: ")
                if not password:
                    break
            else:
                print("Maximum authentication attempts reached")
                return False, None
                
        except Exception as e:
            print(f"✗ Connection error: {str(e)}")
            if ssh_client:
                ssh_client.close()
                ssh_client = None
            return False, None
    
    return False, None

def cleanup_ssh():
    """Clean up SSH connection and temp files"""
    global ssh_client, sftp_client, local_temp_db
    
    if sftp_client:
        try:
            sftp_client.close()
        except:
            pass
    
    if ssh_client:
        try:
            ssh_client.close()
        except:
            pass
    
    if local_temp_db and os.path.exists(local_temp_db.name):
        try:
            os.unlink(local_temp_db.name)
            print(f"✓ Cleaned up temporary files")
        except:
            pass

def export_db_structure(db_file, output_file='database_structure.txt'):
    """Export complete database structure to a text file"""
    
    if not os.path.exists(db_file):
        print(f"Error: Database file '{db_file}' not found!")
        return False
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Generate output filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if remote_mode:
        base_name = os.path.splitext(output_file)[0]
        ext = os.path.splitext(output_file)[1]
        output_file = f"{base_name}_remote_{timestamp}{ext}"
    else:
        base_name = os.path.splitext(output_file)[0]
        ext = os.path.splitext(output_file)[1]
        output_file = f"{base_name}_local_{timestamp}{ext}"
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            # Write header
            f.write("=" * 80 + "\n")
            f.write(f"DATABASE STRUCTURE EXPORT\n")
            f.write(f"Database: {remote_db_path if remote_mode else db_file}\n")
            f.write(f"Connection: {'Remote (SSH)' if remote_mode else 'Local'}\n")
            f.write(f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            # Get all tables
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = cursor.fetchall()
            
            f.write(f"Total Tables: {len(tables)}\n")
            f.write("-" * 80 + "\n\n")
            
            # For each table
            for table_index, (table_name,) in enumerate(tables, 1):
                print(f"Processing table {table_index}/{len(tables)}: {table_name}")
                
                f.write(f"{table_index}. TABLE: {table_name}\n")
                f.write("=" * 60 + "\n\n")
                
                # Get table info
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                # Write column details
                f.write("COLUMNS:\n")
                f.write("-" * 60 + "\n")
                f.write(f"{'Column Name':<25} {'Type':<15} {'Not Null':<10} {'Default':<15} {'PK':<5}\n")
                f.write("-" * 60 + "\n")
                
                for col in columns:
                    col_id, name, col_type, not_null, default, pk = col
                    not_null_str = "YES" if not_null else "NO"
                    pk_str = "YES" if pk else "NO"
                    default_str = str(default) if default is not None else "NULL"
                    if len(default_str) > 15:
                        default_str = default_str[:12] + "..."
                    
                    f.write(f"{name:<25} {col_type:<15} {not_null_str:<10} {default_str:<15} {pk_str:<5}\n")
                
                f.write("\n")
                
                # Get foreign keys
                cursor.execute(f"PRAGMA foreign_key_list({table_name})")
                foreign_keys = cursor.fetchall()
                
                if foreign_keys:
                    f.write("FOREIGN KEYS:\n")
                    f.write("-" * 60 + "\n")
                    for fk in foreign_keys:
                        f.write(f"  {fk[3]} -> {fk[2]}.{fk[4]}")
                        if fk[5]:  # ON UPDATE
                            f.write(f" ON UPDATE {fk[5]}")
                        if fk[6]:  # ON DELETE
                            f.write(f" ON DELETE {fk[6]}")
                        f.write("\n")
                    f.write("\n")
                
                # Get indexes
                cursor.execute(f"PRAGMA index_list({table_name})")
                indexes = cursor.fetchall()
                
                if indexes:
                    f.write("INDEXES:\n")
                    f.write("-" * 60 + "\n")
                    for idx in indexes:
                        idx_name = idx[1]
                        unique = "UNIQUE" if idx[2] else "NON-UNIQUE"
                        f.write(f"  {idx_name} ({unique})\n")
                        
                        # Get index columns
                        cursor.execute(f"PRAGMA index_info({idx_name})")
                        idx_cols = cursor.fetchall()
                        for col in idx_cols:
                            f.write(f"    - {col[2]}\n")
                    f.write("\n")
                
                # Get table creation SQL
                cursor.execute(f"""
                    SELECT sql FROM sqlite_master 
                    WHERE type='table' AND name='{table_name}'
                """)
                create_sql = cursor.fetchone()
                if create_sql and create_sql[0]:
                    f.write("CREATE TABLE SQL:\n")
                    f.write("-" * 60 + "\n")
                    f.write(create_sql[0] + "\n\n")
                
                # Get row count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = cursor.fetchone()[0]
                f.write(f"Row Count: {row_count:,}\n")
                
                # Sample data (first 5 rows)
                if row_count > 0:
                    cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                    sample_rows = cursor.fetchall()
                    
                    f.write("\nSAMPLE DATA (first 5 rows):\n")
                    f.write("-" * 60 + "\n")
                    
                    # Get column names
                    col_names = [col[1] for col in columns]
                    
                    # Calculate column widths
                    col_widths = []
                    for i, name in enumerate(col_names):
                        max_width = len(name)
                        for row in sample_rows:
                            val_str = str(row[i]) if row[i] is not None else "NULL"
                            max_width = max(max_width, len(val_str))
                        col_widths.append(min(max_width, 30))  # Limit to 30 chars
                    
                    # Write header
                    header = ""
                    for name, width in zip(col_names, col_widths):
                        header += f"{name[:width]:<{width}} "
                    f.write(header.strip() + "\n")
                    f.write("-" * len(header) + "\n")
                    
                    # Write data
                    for row in sample_rows:
                        row_str = ""
                        for val, width in zip(row, col_widths):
                            val_str = str(val) if val is not None else "NULL"
                            if len(val_str) > width:
                                val_str = val_str[:width-3] + "..."
                            row_str += f"{val_str:<{width}} "
                        f.write(row_str.strip() + "\n")
                
                f.write("\n" + "=" * 80 + "\n\n")
            
            # Get views
            cursor.execute("""
                SELECT name, sql FROM sqlite_master 
                WHERE type='view'
                ORDER BY name
            """)
            views = cursor.fetchall()
            
            if views:
                print("Processing views...")
                f.write("\nVIEWS:\n")
                f.write("=" * 80 + "\n\n")
                for view_name, view_sql in views:
                    f.write(f"VIEW: {view_name}\n")
                    f.write("-" * 60 + "\n")
                    f.write(view_sql + "\n\n")
            
            # Get triggers
            cursor.execute("""
                SELECT name, sql FROM sqlite_master 
                WHERE type='trigger'
                ORDER BY name
            """)
            triggers = cursor.fetchall()
            
            if triggers:
                print("Processing triggers...")
                f.write("\nTRIGGERS:\n")
                f.write("=" * 80 + "\n\n")
                for trigger_name, trigger_sql in triggers:
                    f.write(f"TRIGGER: {trigger_name}\n")
                    f.write("-" * 60 + "\n")
                    f.write(trigger_sql + "\n\n")
            
            # Database statistics
            print("Collecting database statistics...")
            f.write("\nDATABASE STATISTICS:\n")
            f.write("=" * 80 + "\n")
            
            # Total size
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            db_size = cursor.fetchone()[0]
            f.write(f"Database Size: {db_size:,} bytes ({db_size/1024/1024:.2f} MB)\n")
            
            # SQLite version
            cursor.execute("SELECT sqlite_version()")
            sqlite_version = cursor.fetchone()[0]
            f.write(f"SQLite Version: {sqlite_version}\n")
            
            # Foreign keys status
            cursor.execute("PRAGMA foreign_keys")
            fk_status = cursor.fetchone()[0]
            f.write(f"Foreign Keys Enabled: {'YES' if fk_status else 'NO'}\n")
            
            # Connection info
            if remote_mode:
                f.write(f"Remote Connection: {remote_db_path}\n")
                f.write(f"Local Temp File: {db_file}\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("END OF EXPORT\n")
            f.write("=" * 80 + "\n")
        
        conn.close()
        print(f"✓ Database structure exported to: {output_file}")
        return True, output_file
        
    except Exception as e:
        conn.close()
        print(f"✗ Error during export: {e}")
        return False, None

def export_db_schema_diagram(db_file, output_file='database_schema.txt'):
    """Export a simplified schema diagram"""
    
    if not os.path.exists(db_file):
        print(f"Error: Database file '{db_file}' not found!")
        return False, None
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Generate output filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if remote_mode:
        base_name = os.path.splitext(output_file)[0]
        ext = os.path.splitext(output_file)[1]
        output_file = f"{base_name}_remote_{timestamp}{ext}"
    else:
        base_name = os.path.splitext(output_file)[0]
        ext = os.path.splitext(output_file)[1]
        output_file = f"{base_name}_local_{timestamp}{ext}"
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("DATABASE SCHEMA DIAGRAM\n")
            f.write("=" * 80 + "\n")
            f.write(f"Database: {remote_db_path if remote_mode else db_file}\n")
            f.write(f"Connection: {'Remote (SSH)' if remote_mode else 'Local'}\n")
            f.write(f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            # Get all tables
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = cursor.fetchall()
            
            for (table_name,) in tables:
                f.write(f"┌─ {table_name} " + "─" * (40 - len(table_name)) + "┐\n")
                
                # Get columns
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                for col in columns:
                    col_id, name, col_type, not_null, default, pk = col
                    
                    # Build column string
                    col_str = f"│ {name}"
                    if pk:
                        col_str += " [PK]"
                    col_str += f" : {col_type}"
                    if not_null:
                        col_str += " NOT NULL"
                    if default is not None:
                        col_str += f" DEFAULT {default}"
                    
                    # Pad to box width
                    col_str += " " * (43 - len(col_str)) + "│"
                    f.write(col_str + "\n")
                
                # Get foreign keys
                cursor.execute(f"PRAGMA foreign_key_list({table_name})")
                foreign_keys = cursor.fetchall()
                
                if foreign_keys:
                    f.write("├" + "─" * 43 + "┤\n")
                    for fk in foreign_keys:
                        fk_str = f"│ FK: {fk[3]} -> {fk[2]}.{fk[4]}"
                        fk_str += " " * (43 - len(fk_str)) + "│"
                        f.write(fk_str + "\n")
                
                f.write("└" + "─" * 43 + "┘\n\n")
        
        conn.close()
        print(f"✓ Schema diagram exported to: {output_file}")
        return True, output_file
        
    except Exception as e:
        conn.close()
        print(f"✗ Error during schema export: {e}")
        return False, None

def main():
    """Main function"""
    try:
        # Setup database connection
        success, db_file = choose_database_mode()
        if not success:
            print("Database setup failed. Exiting...")
            return
        
        print(f"\nAnalyzing database: {db_file}")
        print("=" * 50)
        
        # Export options
        print("\nSelect export options:")
        print("1. Full structure export only")
        print("2. Schema diagram only")
        print("3. Both exports")
        
        while True:
            try:
                choice = input("\nEnter choice (1-3): ").strip()
                if choice in ['1', '2', '3']:
                    break
                print("Invalid choice. Please enter 1, 2, or 3.")
            except KeyboardInterrupt:
                print("\nExiting...")
                return
        
        exports_completed = []
        
        # Perform exports
        if choice in ['1', '3']:
            print("\nExporting full database structure...")
            success, output_file = export_db_structure(db_file, 'database_structure_full.txt')
            if success:
                exports_completed.append(output_file)
        
        if choice in ['2', '3']:
            print("\nExporting schema diagram...")
            success, output_file = export_db_schema_diagram(db_file, 'database_schema_simple.txt')
            if success:
                exports_completed.append(output_file)
        
        # Summary
        print(f"\n{'='*60}")
        print("EXPORT SUMMARY")
        print(f"{'='*60}")
        print(f"Database: {'Remote' if remote_mode else 'Local'}")
        if remote_mode:
            print(f"Remote path: {remote_db_path}")
        print(f"Files created: {len(exports_completed)}")
        
        for file_path in exports_completed:
            file_size = os.path.getsize(file_path)
            print(f"  ✓ {file_path} ({file_size:,} bytes)")
        
        print(f"\n✓ Export completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always cleanup SSH connection
        cleanup_ssh()

if __name__ == "__main__":
    main()