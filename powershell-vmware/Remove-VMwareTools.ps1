#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Enhanced script to completely remove VMware Tools from Windows systems

.DESCRIPTION
    This script performs a comprehensive removal of VMware Tools including:
    - Registry entries and MSI installer data
    - Program files and common files
    - Windows services
    - Start menu entries
    - DLL unregistration
    - Network adapter cleanup
    - ProgramData cleanup
    
    Supports Windows Server 2008-2022 and desktop versions.
    Enhanced version combining community improvements from GitHub discussions.

.PARAMETER Force
    Skip confirmation prompts and proceed with removal

.PARAMETER KeepNetworkAdapters
    Skip removal of VMware network adapters (useful if other VMware products are installed)

.EXAMPLE
    .\Remove-VMwareTools-Enhanced.ps1
    
.EXAMPLE
    .\Remove-VMwareTools-Enhanced.ps1 -Force -KeepNetworkAdapters
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$KeepNetworkAdapters
)

# Enhanced logging function
function Write-Log {
    param(
        [string]$Message,
        [ValidateSet('Info', 'Warning', 'Error', 'Success')]
        [string]$Level = 'Info'
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        'Info' { 'White' }
        'Warning' { 'Yellow' }
        'Error' { 'Red' }
        'Success' { 'Green' }
    }
    
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

# Function to get VMware Tools installer IDs
function Get-VMwareToolsInstallerID {
    Write-Log "Searching for VMware Tools installer information..."
    
    try {
        foreach ($item in $(Get-ChildItem Registry::HKEY_CLASSES_ROOT\Installer\Products -ErrorAction SilentlyContinue)) {
            $productName = $item.GetValue('ProductName') -as [string]
            if ($productName -eq 'VMware Tools') {
                $productIcon = $item.GetValue('ProductIcon') -as [string]
                if ($productIcon) {
                    $msiMatch = [Regex]::Match($productIcon, '(?<={)(.*?)(?=})')
                    if ($msiMatch.Success) {
                        Write-Log "Found VMware Tools installer ID" -Level Success
                        return @{
                            reg_id = $item.PSChildName
                            msi_id = $msiMatch.Value
                        }
                    }
                }
            }
        }
    }
    catch {
        Write-Log "Error searching for installer ID: $($_.Exception.Message)" -Level Error
    }
    
    Write-Log "VMware Tools installer ID not found in registry" -Level Warning
    return $null
}

# Function to safely remove registry keys
function Remove-RegistryKey {
    param([string]$Path)
    
    if (Test-Path $Path) {
        try {
            Remove-Item -Path $Path -Recurse -Force -ErrorAction Stop
            Write-Log "Removed registry key: $Path" -Level Success
        }
        catch {
            Write-Log "Failed to remove registry key: $Path - $($_.Exception.Message)" -Level Error
        }
    }
}

# Function to safely remove directories with retry logic
function Remove-DirectoryWithRetry {
    param(
        [string]$Path,
        [int]$MaxRetries = 3
    )
    
    if (-not (Test-Path $Path)) {
        return
    }
    
    for ($i = 1; $i -le $MaxRetries; $i++) {
        try {
            # First pass: remove all files recursively
            Get-ChildItem -Path $Path -Recurse -Force -ErrorAction SilentlyContinue | 
                Where-Object { -not $_.PSIsContainer } | 
                Remove-Item -Force -ErrorAction SilentlyContinue
            
            # Second pass: remove directories
            Get-ChildItem -Path $Path -Recurse -Force -ErrorAction SilentlyContinue | 
                Where-Object { $_.PSIsContainer } | 
                Sort-Object { $_.FullName.Length } -Descending |
                Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            
            # Finally remove the root directory
            Remove-Item -Path $Path -Recurse -Force -ErrorAction Stop
            Write-Log "Removed directory: $Path" -Level Success
            return
        }
        catch {
            if ($i -eq $MaxRetries) {
                Write-Log "Failed to remove directory after $MaxRetries attempts: $Path - $($_.Exception.Message)" -Level Error
            }
            else {
                Write-Log "Retry $i/$MaxRetries for directory: $Path" -Level Warning
                Start-Sleep -Seconds 2
            }
        }
    }
}

# Function to unregister VMware DLLs
function Unregister-VMwareDLLs {
    $dllPaths = @(
        "C:\Program Files\VMware\VMware Tools\vmStatsProvider\win64\vmStatsProvider.dll",
        "C:\Program Files\VMware\VMware Tools\vmStatsProvider\win32\vmStatsProvider.dll"
    )
    
    foreach ($dllPath in $dllPaths) {
        if (Test-Path $dllPath) {
            try {
                Write-Log "Unregistering DLL: $dllPath"
                $process = Start-Process -FilePath "regsvr32.exe" -ArgumentList "/s", "/u", "`"$dllPath`"" -Wait -PassThru
                if ($process.ExitCode -eq 0) {
                    Write-Log "Successfully unregistered: $dllPath" -Level Success
                }
                else {
                    Write-Log "Failed to unregister: $dllPath (Exit code: $($process.ExitCode))" -Level Warning
                }
            }
            catch {
                Write-Log "Error unregistering DLL: $dllPath - $($_.Exception.Message)" -Level Error
            }
        }
    }
}

# Function to remove VMware network adapters
function Remove-VMwareNetworkAdapters {
    if ($KeepNetworkAdapters) {
        Write-Log "Skipping network adapter removal as requested"
        return
    }
    
    Write-Log "Removing VMware network adapters..."
    
    try {
        # Remove VMXNET3 adapters
        $vmxnet3Adapters = Get-NetAdapter | Where-Object { $_.InterfaceDescription -like "*VMXNET3*" }
        foreach ($adapter in $vmxnet3Adapters) {
            Write-Log "Removing VMXNET3 adapter: $($adapter.Name)"
            Remove-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction SilentlyContinue
        }
        
        # Remove VMware network adapters from Device Manager via PowerShell
        $vmwareDevices = Get-PnpDevice | Where-Object { 
            $_.FriendlyName -like "*VMware*" -and 
            $_.Class -eq "Net" 
        }
        
        foreach ($device in $vmwareDevices) {
            try {
                Write-Log "Removing device: $($device.FriendlyName)"
                $device | Disable-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue
                $device | Remove-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue
            }
            catch {
                Write-Log "Failed to remove device: $($device.FriendlyName)" -Level Warning
            }
        }
    }
    catch {
        Write-Log "Error during network adapter cleanup: $($_.Exception.Message)" -Level Error
    }
}

# Main execution starts here
Write-Log "=== Enhanced VMware Tools Removal Script ===" -Level Success
Write-Log "Running on: $env:COMPUTERNAME"
Write-Log "PowerShell Version: $($PSVersionTable.PSVersion)"
Write-Log "OS Version: $([Environment]::OSVersion.VersionString)"

# Get VMware Tools installer information
$vmware_tools_ids = Get-VMwareToolsInstallerID

# Define all registry targets
$reg_targets = @(
    "Registry::HKEY_CLASSES_ROOT\Installer\Features\",
    "Registry::HKEY_CLASSES_ROOT\Installer\Products\",
    "HKLM:\SOFTWARE\Classes\Installer\Features\",
    "HKLM:\SOFTWARE\Classes\Installer\Products\",
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\UserData\S-1-5-18\Products\"
)

# Define file system targets
$filesystem_targets = @(
    "C:\Program Files\VMware",
    "C:\Program Files\Common Files\VMware",
    "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\VMware",
    "C:\ProgramData\VMware"
)

# Build complete target list
$targets = @()

# Add registry targets based on installer ID
if ($vmware_tools_ids) {
    foreach ($item in $reg_targets) {
        $targets += $item + $vmware_tools_ids.reg_id
    }
    # Add MSI installer registry key
    $targets += "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{$($vmware_tools_ids.msi_id)}"
}

# Add legacy registry entries for older Windows versions
if ([Environment]::OSVersion.Version.Major -lt 10) {
    $targets += @(
        "HKCR:\CLSID\{D86ADE52-C4D9-4B98-AA0D-9B0C7F1EBBC8}",
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{9709436B-5A41-4946-8BE7-2AA433CAF108}",
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{FE2F6A2C-196E-4210-9C04-2B1BC21F07EF}"
    )
}

# Add additional registry keys
$additional_registry_keys = @(
    "HKLM:\SOFTWARE\VMware, Inc.",
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\VMware User Process"
)

foreach ($key in $additional_registry_keys) {
    if (Test-Path $key) {
        $targets += $key
    }
}

# Add filesystem targets
foreach ($path in $filesystem_targets) {
    if (Test-Path $path) {
        $targets += $path
    }
}

# Get VMware services
Write-Log "Scanning for VMware services..."
$services = @()
$services += Get-Service -DisplayName "VMware*" -ErrorAction SilentlyContinue
$services += Get-Service -DisplayName "GISvc" -ErrorAction SilentlyContinue

# Display what will be removed
Write-Log "=== REMOVAL SUMMARY ===" -Level Warning
if ($targets.Count -eq 0 -and $services.Count -eq 0) {
    Write-Log "Nothing to do! VMware Tools does not appear to be installed." -Level Success
    exit 0
}

Write-Log "The following items will be removed:"
Write-Log "Registry Keys and Directories:" -Level Warning
$targets | ForEach-Object { Write-Log "  - $_" }

if ($services.Count -gt 0) {
    Write-Log "Services:" -Level Warning
    $services | ForEach-Object { Write-Log "  - $($_.DisplayName) ($($_.Name))" }
}

if (-not $KeepNetworkAdapters) {
    Write-Log "VMware network adapters will also be removed" -Level Warning
}

# Confirmation prompt
if (-not $Force) {
    Write-Log "Continue with removal? (y/N)" -Level Warning
    $confirmation = Read-Host
    if ($confirmation -ne 'y' -and $confirmation -ne 'Y') {
        Write-Log "Operation cancelled by user" -Level Info
        exit 0
    }
}

Write-Log "=== STARTING REMOVAL PROCESS ===" -Level Success

# Step 1: Unregister DLLs
Write-Log "Step 1: Unregistering VMware DLLs..."
Unregister-VMwareDLLs

# Step 2: Stop and remove services
if ($services.Count -gt 0) {
    Write-Log "Step 2: Stopping and removing VMware services..."
    
    # Stop services
    foreach ($service in $services) {
        try {
            Write-Log "Stopping service: $($service.DisplayName)"
            Stop-Service -Name $service.Name -Force -ErrorAction SilentlyContinue
        }
        catch {
            Write-Log "Failed to stop service: $($service.Name)" -Level Warning
        }
    }
    
    # Remove services
    if (Get-Command Remove-Service -ErrorAction SilentlyContinue) {
        foreach ($service in $services) {
            try {
                Remove-Service -Name $service.Name -Confirm:$false -ErrorAction SilentlyContinue
                Write-Log "Removed service: $($service.DisplayName)" -Level Success
            }
            catch {
                Write-Log "Failed to remove service: $($service.Name)" -Level Warning
            }
        }
    }
    else {
        # Fallback for older PowerShell versions
        foreach ($service in $services) {
            try {
                $result = & sc.exe DELETE $service.Name 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Log "Removed service: $($service.DisplayName)" -Level Success
                }
                else {
                    Write-Log "Failed to remove service: $($service.Name) - $result" -Level Warning
                }
            }
            catch {
                Write-Log "Error removing service: $($service.Name)" -Level Warning
            }
        }
    }
}

# Step 3: Stop dependent services for file removal
Write-Log "Step 3: Temporarily stopping dependent services..."
$dependentServices = @()

try {
    # Get dependent services before stopping
    $eventLogDeps = Get-Service -Name "EventLog" -DependentServices -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
    $winmgmtDeps = Get-Service -Name "winmgmt" -DependentServices -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
    
    $dependentServices += $eventLogDeps
    $dependentServices += $winmgmtDeps
    
    # Stop required services
    Stop-Service -Name "EventLog" -Force -ErrorAction SilentlyContinue
    Stop-Service -Name "wmiApSrv" -Force -ErrorAction SilentlyContinue
    Stop-Service -Name "winmgmt" -Force -ErrorAction SilentlyContinue
    
    Write-Log "Waiting for services to stop..."
    Start-Sleep -Seconds 5
}
catch {
    Write-Log "Warning: Could not stop some dependent services" -Level Warning
}

# Step 4: Remove files and registry entries
Write-Log "Step 4: Removing files and registry entries..."
foreach ($target in $targets) {
    if ($target.StartsWith('HKLM:') -or $target.StartsWith('HKCR:') -or $target.StartsWith('Registry::')) {
        Remove-RegistryKey -Path $target
    }
    else {
        Remove-DirectoryWithRetry -Path $target
    }
}

# Step 5: Remove network adapters
Write-Log "Step 5: Removing VMware network adapters..."
Remove-VMwareNetworkAdapters

# Step 6: Restart dependent services
Write-Log "Step 6: Restarting dependent services..."
try {
    Start-Service -Name "EventLog" -ErrorAction SilentlyContinue
    Start-Service -Name "wmiApSrv" -ErrorAction SilentlyContinue
    Start-Service -Name "winmgmt" -ErrorAction SilentlyContinue
    
    # Restart dependent services
    foreach ($serviceName in $dependentServices) {
        try {
            Start-Service -Name $serviceName -ErrorAction SilentlyContinue
        }
        catch {
            # Ignore errors as some services may not need to be restarted
        }
    }
}
catch {
    Write-Log "Warning: Some services may need manual restart" -Level Warning
}

# Final verification
Write-Log "=== VERIFICATION ===" -Level Success
$remainingServices = Get-Service -DisplayName "VMware*" -ErrorAction SilentlyContinue
if ($remainingServices.Count -gt 0) {
    Write-Log "Warning: Some VMware services still exist:" -Level Warning
    $remainingServices | ForEach-Object { Write-Log "  - $($_.DisplayName)" -Level Warning }
}

$remainingFiles = @()
foreach ($path in $filesystem_targets) {
    if (Test-Path $path) {
        $remainingFiles += $path
    }
}

if ($remainingFiles.Count -gt 0) {
    Write-Log "Warning: Some files/directories still exist:" -Level Warning
    $remainingFiles | ForEach-Object { Write-Log "  - $_" -Level Warning }
}

if ($remainingServices.Count -eq 0 -and $remainingFiles.Count -eq 0) {
    Write-Log "VMware Tools removal completed successfully!" -Level Success
}
else {
    Write-Log "VMware Tools removal completed with warnings. See above for details." -Level Warning
}

Write-Log "=== IMPORTANT ===" -Level Warning
Write-Log "A system reboot is REQUIRED to complete the removal process."
Write-Log "Please reboot the system when convenient."

if (-not $Force) {
    $rebootNow = Read-Host "Reboot now? (y/N)"
    if ($rebootNow -eq 'y' -or $rebootNow -eq 'Y') {
        Write-Log "Initiating system reboot..."
        Restart-Computer -Force
    }
}