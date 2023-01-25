function gyre2freqs 
{
    INPUT="$1"

    ## Check that the first input (GYRE file) exists
    if [ ! -e "$INPUT" ]; then
        echo "Error: Cannot locate GYRE file $INPUT"
        exit 1
    fi

    ## Pull out the name of the GYRE file
    bname="$(basename $INPUT)"
    fname="${bname%%.*}-freqs"

    ## Create a directory for the results and go there
    path=$(dirname "$INPUT")/"$fname"
    mkdir -p "$path" 
    cd "$path" 


    logfile="gyre-l0.log"
    #exec > $logfile 2>&1

    ## Create a gyre.in file to find the large frequency separation
    echo "&model
        model_type = 'EVOL'
        file = '../$INPUT'
        file_format = 'FGONG'
    /

    &constants
    /

    &mode
        l=0
    /
    &mode
        l=1
    /

    &osc
        inner_bound = 'ZERO_R'
    /

    &num
        diff_scheme = 'MAGNUS_GL2'
    /

    &scan
        freq_min_units = 'CYC_PER_DAY'
        freq_max_units = 'CYC_PER_DAY'
        grid_type = 'LINEAR'

        freq_min = 15 !fminauto
        freq_max = 95 !fmaxauto
        n_freq = 100
    /

    &grid
        x_i = 0.00001
        w_osc = 10
        w_exp = 2
        w_ctr = 10
    /

    &rot
    /

    &ad_output
        freq_units = 'CYC_PER_DAY'
        summary_file = 'profile1-freqs.dat'
        summary_file_format = 'TXT'
        summary_item_list = 'l, n_pg, n_p, n_g, freq, E_norm'
    /

    &nad_output
    /

    " >| "gyre.in"

    
    ## Run GYRE
    $GYRE_DIR/bin/gyre gyre.in &>gyre.out

    ### Hooray!
    cp "$INPUT.dat" ..
    echo "Conversion complete. Results can be found in $INPUT.dat"
    rm -rf *
    currdir=$(pwd)
    cd ..
    rm -rf "$currdir"
    exit 0
    echo "Something went wrong. Perhaps the following will help:"
    cat gyre.out
    cd ..
}


cd dsct/LOGS
for FGONG in *.FGONG; do
    echo $FGONG
    gyre2freqs $FGONG
done
