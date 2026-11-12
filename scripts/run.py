"""Run the public Kalanos CLI on a local path. No MCP or publication."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ALLOWED_EXTRAS = {"hf", "hdf5", "mcap", "numeric", "video", "all"}

def boolean(env, key, default):
    value = env.get(key, default)
    if value not in {"true", "false"}:
        raise ValueError(key + " must be true or false")
    return value == "true"

def config(env):
    source = env.get("INPUT_PATH", "")
    if not source or "://" in source or "\n" in source or "\r" in source:
        raise ValueError("path must name a local file or directory, not a remote URI")
    path = Path(source).resolve(strict=True)
    if not path.is_file() and not path.is_dir():
        raise ValueError("path must be a regular file or directory")
    statuses = [x.strip() for x in env.get("INPUT_FAIL_ON", "blocked,review,unknown").split(",")]
    if not statuses or any(x not in {"blocked", "review", "unknown"} for x in statuses):
        raise ValueError("invalid fail-on statuses")
    version = env.get("INPUT_VERSION", "0.9.3")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:rc[0-9]+)?", version):
        raise ValueError("version must be an exact release version")
    extras = [x.strip() for x in env.get("INPUT_EXTRAS", "").split(",") if x.strip()]
    if not set(extras) <= ALLOWED_EXTRAS:
        raise ValueError("unsupported package extra")
    tier = env.get("INPUT_TIER", "")
    if tier and tier not in {"metadata", "standard", "full"}:
        raise ValueError("unsupported tier")
    timeout = int(env.get("INPUT_TIMEOUT", "1800"))
    if not 1 <= timeout <= 86400:
        raise ValueError("timeout must be 1..86400 seconds")
    return {"path": path, "fail_on": ",".join(dict.fromkeys(statuses)),
            "version": version, "extras": extras, "tier": tier, "timeout": timeout,
            "profile": env.get("INPUT_PROFILE", ""),
            "map_file": env.get("INPUT_MAP_FILE", ""),
            "install": boolean(env,"INPUT_INSTALL","true"),
            "summary": boolean(env,"INPUT_SUMMARY","false"),
            "hash_source": boolean(env,"INPUT_HASH_SOURCE","false"),
            "no_sidecar": boolean(env,"INPUT_NO_SIDECAR","false"),
            "executable": env.get("INPUT_EXECUTABLE","kalanos")}

def command(cfg, executable, report):
    args = [executable, "grade", str(cfg["path"]), "--report", str(report),
            "--fail-on", cfg["fail_on"], "--no-color"]
    for key, flag in (("profile","--profile"),("map_file","--map-file"),("tier","--tier")):
        if cfg[key]:
            args.extend([flag,cfg[key]])
    if cfg["hash_source"]:
        args.append("--hash-source")
    if cfg["no_sidecar"]:
        args.append("--no-sidecar")
    return args

def report_counts(report):
    # The CLI owns gate semantics. These checks prevent a missing/malformed output
    # from being presented as a successful assessment by the wrapper.
    data = json.loads(report.read_text())
    counts = data.get("eligibility_counts")
    if not isinstance(counts, dict):
        raise ValueError("report lacks decision counts")
    keys = ("total","pass_count","blocked","review","unknown")
    if any(type(counts.get(k)) is not int or counts[k] < 0 for k in keys):
        raise ValueError("invalid report counts")
    if sum(counts[k] for k in keys[1:]) != counts["total"] or counts["total"] == 0:
        raise ValueError("empty or inconsistent report inventory")
    if type(counts.get("inventory_complete")) is not bool:
        raise ValueError("inventory completeness missing")
    return {k: counts[k] for k in (*keys,"inventory_complete")}

def run(env=None):
    env = dict(os.environ if env is None else env)
    out = None
    code = 2
    result = {"status":"error","exit_code":2}
    try:
        cfg = config(env)
        # Keep output outside the dataset so recursive discovery cannot regrade it.
        temp_root = Path(env.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
        if temp_root == cfg["path"] or temp_root.is_relative_to(cfg["path"]):
            raise ValueError("runner temp must be outside the input dataset")
        out = Path(tempfile.mkdtemp(prefix="kalanos-action-",dir=temp_root))
        out.chmod(0o700)
        executable = cfg["executable"]
        if cfg["install"]:
            venv = out / "venv"
            with (out / "install.log").open("w") as log:
                subprocess.run([sys.executable,"-m","venv",str(venv)],check=True,
                               stdout=log,stderr=log,timeout=120)
                python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                package = "kalanos" + ("["+",".join(cfg["extras"])+"]" if cfg["extras"] else "")
                subprocess.run([str(python),"-m","pip","install","--disable-pip-version-check",
                                package+"=="+cfg["version"]],check=True,
                               stdout=log,stderr=log,timeout=600)
            executable = str(venv / ("Scripts/kalanos.exe" if os.name == "nt" else "bin/kalanos"))
        elif shutil.which(executable) is None:
            raise ValueError("preinstalled kalanos executable not found")
        report = out / "audit.json"
        child_env = dict(env)
        # No publication is invoked; remove commonly used Hub credentials anyway.
        child_env.pop("KALANOS_API_KEY",None)
        child_env["NO_COLOR"] = "1"
        with (out / "grader.log").open("w") as log:
            completed = subprocess.run(command(cfg,executable,report),env=child_env,
                                       stdout=log,stderr=log,timeout=cfg["timeout"])
        code = completed.returncode if completed.returncode in {0,1,2} else 2
        result = {"status":{0:"pass",1:"fail",2:"error"}[code],"exit_code":code,
                  "fail_on":cfg["fail_on"],
                  "grader_version_requested":cfg["version"] if cfg["install"] else None,
                  "install_mode":"isolated" if cfg["install"] else "preinstalled"}
        if code in {0,1}:
            result["counts"] = report_counts(report)
        if cfg["summary"] and env.get("GITHUB_STEP_SUMMARY"):
            # Only fixed labels, validated numeric counts and fixed statuses.
            lines = ["## Kalanos dataset audit","", "**"+result["status"].upper()+"**",""]
            if "counts" in result:
                lines += ["| Decision | Episodes |","|---|---:|"]
                lines += ["| "+k+" | "+str(result["counts"][k])+" |"
                          for k in ("pass_count","review","blocked","unknown")]
                lines += ["", "Inventory complete: "+str(result["counts"]["inventory_complete"])]
            lines += ["", "Gate statuses: "+cfg["fail_on"],
                      "", "A gate pass is not a minimum score, task-success or training-performance guarantee.",
                      "Report-only findings may remain. Inspect the retained audit.", ""]
            with open(env["GITHUB_STEP_SUMMARY"],"a") as summary:
                summary.write("\n".join(lines))
    except Exception as exc:
        code = 2
        result = {"status":"error","exit_code":2,"error_type":type(exc).__name__,
                  "message":"Audit could not complete; inspect local logs if available."}
    if out:
        (out / "result.json").write_text(json.dumps(result,indent=2)+"\n")
    if env.get("GITHUB_OUTPUT"):
        with open(env["GITHUB_OUTPUT"],"a") as output:
            output.write("status="+result["status"]+"\nexit-code="+str(code)+"\n")
            if out:
                # GitHub runner temp names are controlled by the runner; protect output protocol.
                if "\n" in str(out) or "\r" in str(out):
                    return 2
                output.write("output-directory="+str(out)+"\n")
                if (out / "audit.json").is_file():
                    output.write("report-path="+str(out / "audit.json")+"\n")
    print("Kalanos audit: "+result["status"]+" (exit "+str(code)+")")
    return code

if __name__ == "__main__":
    sys.exit(run())
