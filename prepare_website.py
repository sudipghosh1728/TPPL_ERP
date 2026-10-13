"""Build the supplied corporate site for the local combined preview."""
import pathlib, shutil, subprocess
root=pathlib.Path(__file__).resolve().parent
website=root/'TPPL'
if not (website/'package.json').exists():raise SystemExit('The supplied TPPL folder is missing.')
subprocess.run([shutil.which('npm.cmd') or 'npm','run','build'],cwd=website,check=True)
shutil.copytree(website/'dist',root/'public'/'website',dirs_exist_ok=True)
print('Corporate website ready at /; ERP stays at /admin and /user. No deployment performed.')
