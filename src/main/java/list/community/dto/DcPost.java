package list.community.dto;

public class DcPost {
    private String title;
    private String views;
    private String likes;

    public DcPost(String title, String views, String likes) {
        this.title = title;
        this.views = views;
        this.likes = likes;
    }

    public String getTitle(){
        return title;
    }

    public String getViews(){
        return views;
    }

    public String getLikes(){
        return likes;
    }
}
