#!/bin/bash
ARRAY_JOB_ID=$(sbatch --parsable $HOME/molspin_run_workspace/job_script.sh)
EPILOGUE_JOB_ID=$(sbatch --parsable \
       --dependency=afterok:$ARRAY_JOB_ID \
       --export=ALL,SLURM_ARRAY_JOB_ID=$ARRAY_JOB_ID \
       $HOME/molspin_run_workspace/epilogue_script.sh)
echo "SUBMITTED:$ARRAY_JOB_ID,$EPILOGUE_JOB_ID"
