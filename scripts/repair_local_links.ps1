param([Parameter(Mandatory = $true)][string]$PreviousProjectRoot, [switch]$Apply)
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$dependencyRoot = Join-Path $projectRoot 'apps\web\node_modules'
$oldRoot = [IO.Path]::GetFullPath($PreviousProjectRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$repaired = 0
function Repair-Links([string]$directory) {
    foreach ($entry in Get-ChildItem -LiteralPath $directory -Force) {
        if ($entry.LinkType) {
            $target = [string]$entry.Target
            if ($target.StartsWith($oldRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
                $replacement = $projectRoot + $target.Substring($oldRoot.Length)
                $localPath = [IO.Path]::GetFullPath($entry.FullName)
                if (!$localPath.StartsWith($dependencyRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Link is outside project dependencies.' }
                if (!$replacement.StartsWith($dependencyRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Replacement is outside project dependencies.' }
                if (!(Test-Path -LiteralPath $replacement)) { throw "Missing installed dependency: $replacement" }
                if (-not $Apply) { Write-Output "Would repair $localPath -> $replacement"; continue }
                # Remove only the junction itself; never recurse into its target.
                [IO.Directory]::Delete($localPath)
                New-Item -ItemType Junction -Path $localPath -Target $replacement | Out-Null
                $script:repaired++
            }
        } elseif ($entry.PSIsContainer -and $entry.Name -notin @('.vite', '.vite-temp')) {
            Repair-Links $entry.FullName
        }
    }
}
Repair-Links $dependencyRoot
Write-Output "Repaired $repaired project-local dependency links."
