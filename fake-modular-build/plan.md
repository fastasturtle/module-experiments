1. Take existing project, build it (with self-built unmodified clang), measure time (**T_orig**), create **CDB_orig**
1. Generate **Ninja_orig** from **CDB_orig**, build it, measure time (**T_ninja_parallel**), first unavoidable delta
(**D_obj_only** = **Torig** - **T_ninja_parallel**)
    1. Extract and save source <-> obj mapping from it
    1. Extract and save preamble locations
1. Replace compiler in **Ninja_orig** with measuring compiler (**Ninja_measuring**), run compilation, locate and
collect traces.
1. Extract dependency forest from traces
    1. filter out non-preamble includes
    1. notify if it changes between invocations
1. Extract self-times for each node in each dependency tree
    1. Also don't forget self-times for sources (require putting back traces in the driver)
    1. notify if they diverge too much
    1. note: total-time = self-time + sum of includer's total-times
1. Construct **Ninja_fake_modules** script, measure build time (**T_ninja_modules**):
    1. Assume each header corresponds with a module 1:1
    1. Each "module"/source file correspond with a fake "artifact" 
    1. Each build edge connects module/source file to its immediately "imported modules"
    1. Build rule is wait it's self-time and touch fake artifact
    
**T_ninja_modules** + **D_obj_only** is the estimated modular build time.
    
Also repeat everything, but modify **Ninja_orig**:
- `-fsyntax-only`
- `-g -O0`
- `-g -O2`
- `-O2`
- different parallelism in Ninja
- different "BMI load time": for each TU add (p * (total-time - self-time)) to fake processing time
- try squashing small headers (if total-time < treshold => don't create separate compilation,
add to includer's self-time instead)
    
Known bias:
- Pending template instantiations are still happening at the end of TU, not inside modules (so they are repeated
across different TUs) (pro-modules)
- Non-modular case is built with additional parallelism, modular build could catch up on contention points (pro-modules)
- It's not clear what the average "Loading BMI" time would be (cons-modules)
- Real-world modular projects might be structured differently
- It's not clear for me at what point codegen and optimiztions would happen, and whether **D_obj_only** is accurate
