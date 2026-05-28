# DefCon Toronto 2026, live demo plan

Status: Draft
Event: DefCon Toronto, May 2026
Length: 15 minutes (inside the 40 minute talk)
Success criteria: full kill chain end to end, live, without breaking, under 10 minutes

## Goal

Prove the framework works by running it in front of the room.

Kill chain:
1. Recon a GOAD lab from zero knowledge
2. Capture NTLM hashes
3. Crack them on the Cracker VM
4. Have the analyst agent summarize what was found
5. Close the session

All from a single Claude Code prompt at the top of the demo.

## Pre demo setup (done before the talk)

- Proxmox host on the demo laptop (or the venue's reliable wired connection to a staged host)
- All v0.1 VMs provisioned and snapshotted clean
- GOAD lab pre provisioned, snapshot reverted to clean state for the live run
- `eidolon` CLI on the demo Mac, mTLS + WireGuard to the Proxmox host verified
- Claude Code signed in, all subagent definitions loaded
- Backup pre recorded video of the demo in case of network failure (never say this out loud, just have it ready)
- Clean browser tabs: public repo, docs, architecture overview diagram
- Terminal font size big enough for the room (at least 18pt)

## Backup plan

Two layers:

1. Local fallback: if the Proxmox host is unreachable, demo runs against a local Mac mini with the same VM templates
2. Video fallback: pre recorded demo plays in place of the live run, narrated live

If something breaks mid demo and cannot be recovered in under 30 seconds, switch to narrated explanation. Do not fight it on stage.

## The live run

### Step 0: show the starting state (30 seconds)

Terminal up. Empty directory. Claude Code open. No running sessions.

Say: "this laptop runs Claude Code. The Proxmox host behind me runs nothing for this client. In 10 minutes we will have done recon, cracked hashes, and written a summary of findings."

### Step 1: start a session (1 minute)

```
$ eidolon session start goad-demo --purpose training --scope ./goad-scope.json
```

What to say:

- Scope token issued
- Sandbox workspace provisioned
- Recon VM pulled from template, pinned to the GOAD VNET
- Every action from here on carries the scope token

Show the scope token (hashed form) on screen briefly.

### Step 2: recon (3 minutes)

Open Claude Code, type:

> "Recon the GOAD network. Start with nmap host discovery, then enumerate interesting services, then nuclei against anything web facing. Summarize what you find."

What to say while it runs:

- The `recon-agent` subagent handles this
- Every nmap, nuclei, httpx call goes through the orchestrator
- Orchestrator validates scope, forwards to the Recon VM's FastAPI server
- Results stream back over SSE

Show the scope token validation in the orchestrator log on a second terminal.

Expected output: 5-8 hosts, one or two web services, the DC, the AD clients, maybe the Jenkins shoehorned into GOAD.

### Step 3: hash capture (2 minutes)

Tell Claude Code:

> "Target the DC. Try to pull NTDS. If that works, send the hashes to the cracker queue."

What to say:

- This step requires operator confirm (impacket secretsdump is a confirm tier action)
- Watch the confirm prompt appear in the Claude Code session
- Approve it
- secretsdump runs, hash file lands in the sandbox
- `cracker-agent` submits to CrackQ on the Cracker VM

### Step 4: crack (4 minutes)

CrackQ processes the hashes. NTLM on a small lab is fast. Expect results in 60-180 seconds for the first few weak passwords.

What to say while it runs:

- The cracker VM has an RX 7600 XT on PCIe passthrough
- Hashcat runs straight against the GPU
- Progress streams through the orchestrator back to Claude Code
- All log lines tagged with the session ID go to the Logger VM

Show the Logger VM audit trail briefly on a third terminal.

### Step 5: analyst summary (2 minutes)

Tell Claude Code:

> "Have the analyst agent summarize this session. What did we find, what got cracked, what would a finding look like."

What to say:

- `analyst-agent` routes through LiteLLM. Demo session runs with egress disabled, so the summary lands on the local models on the LLM Analyst VM. For an egress-allowed session, the same agent call would hit Gemini.
- In either path, agent code does not change. The router does.
- The draft finding prose is the kind of output that an operator would edit into a report

Expected output: a structured summary with hosts, services, cracked accounts, and a draft finding pointing at the weak passwords or the AD misconfig.

### Step 6: close (1 minute)

```
$ eidolon session close goad-demo
```

What to say:

- Sandbox workspace archived locally (operator keeps)
- Scope token revoked
- VMs reverted to their clean template for the next session
- Logger VM still has the audit trail

Final line: "That was 10 minutes. No SaaS. No vendor lock in. The entire stack is in the public repo at <url>."

## If we run short (under 8 minutes)

Add:

- Show the architecture diagram
- Swap the planner model from Gemini to OpenAI in the LiteLLM config live, rerun the analyst summary
- Show the scope token refuse an out of scope command (try to scan a CIDR not in the scope doc, watch it get rejected)

## If we run long (over 12 minutes)

Cut:

- Skip the Logger VM audit trail show
- Skip the model swap demo
- Go straight from analyst summary to close

## What must not break

- Claude Code subagent loading
- WireGuard + mTLS from the demo laptop to the Proxmox host
- Recon VM reaching the GOAD network
- Cracker VM finishing at least two hashes in the allotted time

If any of these four break, the demo breaks. Test each in the 24 hours before the talk.

## Post demo

Take a single screenshot of the final analyst summary. Post it with a link to the repo on the conference hashtag.

Keep the demo VMs running for 30 minutes after the talk in case anyone wants to see it up close at the speaker table.
