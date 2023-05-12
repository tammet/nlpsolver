% rebase('layout.tpl', title='Solve Logic')

<div class="container">
    <div class="row">
        <div class="col">
            <h2>Solve Logic</h2>
            <form method="post" action="/">
                <div class="form-group">
                    <textarea class="form-control" id="passage" name="passage" rows="5">{{passage}}</textarea>
                </div>
                <button type="submit" class="btn btn-outline-primary mt-2">Answer Question</button>
            </form>

            % if result:
            <h2>Answer</h2>
            <pre>{{ result["answer"] }}</pre>
            % end

        </div>
        <div class="col">
            % if result:
            <h2>Output</h2>
            <pre >{{ result["raw"] }}</pre>
            % end
        </div>
    </div>
</div>



