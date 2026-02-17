# Unity C# to Visual Scripting Converter

A comprehensive Python tool that converts Unity C# Scripts (.cs) into Unity Visual Scripting/Bolt Graphs (.asset).

## Overview

This converter transforms Unity C# code into Visual Scripting graphs by:
1. Parsing C# code to extract classes, methods, fields, and statements
2. Mapping C# constructs to Visual Scripting nodes (units)
3. Generating proper JSON-serialized graph data
4. Wrapping in Unity's YAML .asset format

## Features

### Supported C# Constructs

| C# Construct | Visual Scripting Node |
|--------------|----------------------|
| `Start()`, `Update()`, `Awake()`, etc. | Event Units (Unity.VisualScripting.Start, etc.) |
| `Debug.Log()` | InvokeMember (UnityEngine.Debug.Log) |
| `if` statements | If Unit (Unity.VisualScripting.If) |
| Variable assignments | SetVariable Unit |
| String literals | Literal Unit |
| Method calls | InvokeMember Unit |

### Supported Unity Events
- `Start` → `Unity.VisualScripting.Start`
- `Update` → `Unity.VisualScripting.Update`
- `Awake` → `Unity.VisualScripting.Awake`
- `OnEnable` → `Unity.VisualScripting.OnEnable`
- `OnDisable` → `Unity.VisualScripting.OnDisable`
- `OnDestroy` → `Unity.VisualScripting.OnDestroy`
- `FixedUpdate` → `Unity.VisualScripting.FixedUpdate`
- `LateUpdate` → `Unity.VisualScripting.LateUpdate`
- `OnTriggerEnter` → `Unity.VisualScripting.OnTriggerEnter`
- `OnTriggerExit` → `Unity.VisualScripting.OnTriggerExit`
- `OnTriggerStay` → `Unity.VisualScripting.OnTriggerStay`
- `OnCollisionEnter` → `Unity.VisualScripting.OnCollisionEnter`
- `OnCollisionExit` → `Unity.VisualScripting.OnCollisionExit`
- `OnCollisionStay` → `Unity.VisualScripting.OnCollisionStay`

## Installation

No installation required. Just Python 3.7+.

```bash
# Download the converter
wget https://raw.githubusercontent.com/your-repo/cs_to_visual_scripting_converter.py

# Or clone the repository
git clone https://github.com/your-repo/unity-cs-to-visual-scripting.git
```

## Usage

### Convert a Single File

```bash
python cs_to_visual_scripting_converter.py MyScript.cs
```

### Convert with Custom Output Directory

```bash
python cs_to_visual_scripting_converter.py MyScript.cs -o ./Output/Graphs/
```

### Convert All Files in a Directory

```bash
# Non-recursive
python cs_to_visual_scripting_converter.py ./Scripts/

# Recursive (includes subdirectories)
python cs_to_visual_scripting_converter.py ./Scripts/ -r
```

### Command Line Options

```
usage: cs_to_visual_scripting_converter.py [-h] [-o OUTPUT] [-r] input

Convert Unity C# Scripts to Visual Scripting Graphs

positional arguments:
  input                 Input C# file or directory

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output directory (default: same as input)
  -r, --recursive       Process directories recursively
```

## Example

### Input C# Code

```csharp
using UnityEngine;

public class PlayerController : MonoBehaviour
{
    public float speed = 5.0f;
    public int health = 100;
    
    void Start()
    {
        Debug.Log("Player initialized!");
        health = 100;
    }
    
    void Update()
    {
        Debug.Log("Updating player...");
        
        if (health <= 0)
        {
            Debug.Log("Player died!");
        }
    }
}
```

### Output Visual Scripting Graph

The converter generates a `.asset` file with:
- **Start Event** node connected to Debug.Log("Player initialized!")
- **Update Event** node connected to:
  - Debug.Log("Updating player...")
  - If node checking health <= 0
  - Debug.Log("Player died!") in the if branch
- **SetVariable** node for health assignment
- All proper **ControlConnections** (flow) and **ValueConnections** (data)

## Visual Scripting Format

The generated `.asset` files follow Unity's Visual Scripting serialization format:

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!114 &11400000
MonoBehaviour:
  m_ObjectHideFlags: 0
  ...
  _data:
    _json: '{...}'  # JSON-serialized graph
    _objectReferences: []
```

### JSON Graph Structure

```json
{
  "nest": {
    "source": "Embed",
    "macro": null,
    "embed": {
      "variables": {...},
      "controlInputDefinitions": [],
      "controlOutputDefinitions": [],
      "valueInputDefinitions": [],
      "valueOutputDefinitions": [],
      "title": "GraphName",
      "summary": "Converted from ScriptName.cs",
      "pan": {"x": 0.0, "y": 0.0},
      "zoom": 1.0,
      "elements": [
        // Nodes (Units) and Connections
      ]
    }
  }
}
```

## Architecture

### Components

1. **CSharpParser**: Parses C# code using regex patterns
   - Extracts usings, namespace, class definition
   - Extracts fields with types and access modifiers
   - Extracts methods with parameters and bodies

2. **VisualScriptingGenerator**: Generates Visual Scripting graph
   - Creates event nodes for Unity lifecycle methods
   - Creates invoke nodes for method calls
   - Creates flow nodes for conditionals
   - Creates data nodes for literals and variables
   - Establishes connections between nodes

3. **CS_to_VisualScripting_Converter**: Main converter class
   - Orchestrates parsing and generation
   - Handles file I/O
   - Formats output as Unity .asset

### Node Types

| Category | Description |
|----------|-------------|
| EVENT | Entry points (Start, Update, etc.) |
| FLOW | Control flow (If, Sequence, While) |
| DATA | Literals and constants |
| INVOKE | Method calls |
| VARIABLE | Get/Set variable operations |

## Limitations

Current version has the following limitations:

1. **Simplified Control Flow**: Complex nested if/else, loops, and switch statements require manual refinement
2. **Limited Method Support**: Only Debug.Log is fully supported; other methods need manual configuration
3. **No Generic Types**: Generic method/type support is limited
4. **No Custom Classes**: Custom class references need manual handling
5. **No Comments**: C# comments are not preserved in the graph

## Future Enhancements

- [ ] Support for loops (for, while, foreach)
- [ ] Support for switch statements
- [ ] Better handling of arithmetic operations
- [ ] Support for coroutines (IEnumerator)
- [ ] Support for custom method calls
- [ ] Preservation of comments as node descriptions
- [ ] Better layout algorithms for node positioning
- [ ] Support for State Graphs (in addition to Script Graphs)

## Technical Details

### Research Sources

This tool was developed based on research from:
- Unity Visual Scripting Documentation [^1^][^4^][^18^]
- Unity Discussions and Forums [^2^][^32^][^58^]
- Bolt Visual Scripting API Reference [^6^][^50^]
- YAML Serialization Format [^37^][^40^]

### Compatibility

- Unity 2021.1+ (built-in Visual Scripting)
- Unity 2019/2020 LTS with Bolt Asset Store package
- Visual Scripting package 1.5+

## License

MIT License - Free for personal and commercial use.

## Contributing

Contributions are welcome! Please submit pull requests or open issues for:
- Bug fixes
- New feature implementations
- Documentation improvements
- Test cases

## Troubleshooting

### Common Issues

1. **"No .cs files found"**
   - Check that the input path is correct
   - Ensure files have `.cs` extension

2. **Generated graph doesn't open in Unity**
   - Verify Unity Visual Scripting package is installed
   - Check Unity version compatibility
   - Try regenerating unit options in Unity (Tools > Visual Scripting)

3. **Nodes appear disconnected**
   - Some complex control flows may need manual connection
   - Check that method bodies are properly formatted

## Support

For questions, issues, or feature requests:
- Open an issue on GitHub

---

**Note**: This tool converts code structure to visual nodes. The generated graphs should be reviewed and tested in Unity. Some manual adjustments may be needed for complex scripts.
