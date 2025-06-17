package list.community.dto;

public class DogdripPost {
    private String title;
    private String likes;
    private String replys;

    public DogdripPost(String title, String likes, String replys){
        this.title = title;
        this.likes = likes;
        this.replys = replys;
    }

    public String getTitle(){
        return title;
    }

    public String getLikes(){
        return likes;
    }

    public String getReplys(){
        return replys;
    }
}
