import traceback
try:
    import main
    main.main()
except Exception as e:
    print('ERROR:', e)
    traceback.print_exc()
